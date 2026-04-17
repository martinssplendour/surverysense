"""Orchestrates the full topic-analysis pipeline: validation, text prep, embeddings, clustering, labelling, and translation."""
from __future__ import annotations

import logging
from collections import defaultdict
from typing import Iterable

import pandas as pd

from app.core.exceptions import TopicAnalysisDependencyError, TopicAnalysisInputError
from app.services.topic_label_ai_service import TopicAiLabelService
from app.services.topic_analysis_services.bertopic_service import BertopicAnalysisService
from app.services.topic_analysis_services.config import (
    PreparedDocument,
    TopicAnalysisConfig,
)
from app.services.topic_analysis_services.embedding_service import SentenceEmbeddingService
from app.services.topic_analysis_services.example_selection_service import RepresentativeExampleSelectionService
from app.services.topic_analysis_services.hdbscan_service import HdbscanAnalysisService
from app.services.topic_analysis_services.keyword_service import TopicAnalysisKeywordService
from app.services.topic_analysis_services.kmeans_service import KMeansAnalysisService
from app.services.topic_analysis_services.narrative_service import TopicAnalysisNarrativeService
from app.services.topic_analysis_services.ngram_service import NgramAnalysisService
from app.services.topic_analysis_services.text_preparation_service import TopicAnalysisTextPreparationService
from app.services.topic_analysis_services.validation_service import TopicAnalysisInputValidationService


logger = logging.getLogger(__name__)


class TopicAnalysisService:
    """End-to-end topic analysis service that routes to the appropriate model (BERTopic, K-means, HDBSCAN, n-grams)."""

    def __init__(
        self,
        *,
        config: TopicAnalysisConfig,
        input_validation_service: TopicAnalysisInputValidationService,
        text_preparation_service: TopicAnalysisTextPreparationService,
        keyword_service: TopicAnalysisKeywordService,
        narrative_service: TopicAnalysisNarrativeService,
        representative_example_service: RepresentativeExampleSelectionService,
        embedding_service: SentenceEmbeddingService,
        ngram_service: NgramAnalysisService,
        kmeans_service: KMeansAnalysisService,
        hdbscan_service: HdbscanAnalysisService,
        bertopic_service: BertopicAnalysisService,
        ai_label_service: TopicAiLabelService | None = None,
    ) -> None:
        self.config = config
        self.input_validation_service = input_validation_service
        self.text_preparation_service = text_preparation_service
        self.keyword_service = keyword_service
        self.narrative_service = narrative_service
        self.representative_example_service = representative_example_service
        self.embedding_service = embedding_service
        self.ngram_service = ngram_service
        self.kmeans_service = kmeans_service
        self.hdbscan_service = hdbscan_service
        self.bertopic_service = bertopic_service
        self.ai_label_service = ai_label_service

    def warm_up(self) -> None:
        """Pre-load the embedding model and trigger JIT compilation for UMAP/PyTorch at server startup."""
        self.text_preparation_service.warm_up()
        self.embedding_service.warm_up(
            model_name=self.config.embedding_model,
            local_model_path=self.config.embedding_local_path,
        )
        # Trigger Numba JIT compilation for UMAP at startup so the first real BERTopic
        # run doesn't pay a cold-start penalty. Parameters must match the actual BERTopic
        # run: n_neighbors=10, n_components=5, input shape (N, 50) after PCA pre-reduction.
        # Using mismatched params (e.g. n_components=2) compiles different Numba kernels
        # and leaves the real run's kernels uncompiled.
        try:
            import numpy as _np
            import umap as _umap
            _dummy = _np.random.default_rng(0).random((50, 50))
            _umap.UMAP(n_neighbors=10, n_components=5, random_state=42).fit_transform(_dummy)
        except Exception:
            pass

    def run(
        self,
        *,
        result_id: str,
        dataframe: pd.DataFrame,
        model_key: str,
        text_column_name: str,
        available_verbatim_columns: Iterable[str],
    ) -> dict[str, object]:
        """Run the full analysis pipeline and return a serialisable result dict.

        Always returns a dict (never raises); on error, 'ok' is False and 'error' contains the message.
        """
        model_label = self.input_validation_service.get_model_label(model_key)
        base_response: dict[str, object] = {
            "ok": False,
            "result_id": result_id,
            "model_key": model_key,
            "model_label": model_label,
            "text_column_name": text_column_name,
            "filtered_row_count": int(len(dataframe)),
            "valid_document_count": 0,
            "skipped_document_count": 0,
            "translated_document_count": 0,
            "warnings": [],
            "error": None,
            "groups": [],
            "ngram_buckets": [],
            "scatter_points": [],
        }

        try:
            self.input_validation_service.validate_request(
                model_key=model_key,
                text_column_name=text_column_name,
                available_verbatim_columns=available_verbatim_columns,
            )
            prepared = self.text_preparation_service.prepare(
                dataframe,
                text_column_name=text_column_name,
            )
            warnings = self.input_validation_service.validate_dataset(
                prepared,
                model_key=model_key,
            )
            base_response["valid_document_count"] = int(len(prepared.documents))
            base_response["skipped_document_count"] = int(prepared.skipped_row_count)
            base_response["warnings"] = warnings

            embeddings = None
            if model_key == "ngrams":
                ngram_buckets = self.ngram_service.run(
                    prepared.documents,
                    top_n=self.config.top_ngrams_per_bucket,
                )
                translated_bucket_count, translation_warnings = self._translate_ngram_buckets(ngram_buckets)
                warnings.extend(translation_warnings)
                base_response["warnings"] = warnings
                base_response["ok"] = True
                base_response["translated_document_count"] = translated_bucket_count
                base_response["ngram_buckets"] = ngram_buckets
                return base_response

            clustering_texts = list(prepared.texts)
            # BERTopic uses its own internal UMAP+HDBSCAN and expects raw embeddings;
            # K-means and HDBSCAN receive embeddings in a separate branch below.
            if model_key == "bertopic":
                embeddings = self.embedding_service.encode(
                    clustering_texts,
                    model_name=self.config.embedding_model,
                    local_model_path=self.config.embedding_local_path,
                )
                model_result = self.bertopic_service.run(
                    clustering_texts,
                    embeddings,
                    top_terms=self.config.top_terms_per_group,
                    language=self.config.bertopic_language,
                    reduce_outliers=self.config.bertopic_reduce_outliers,
                    outlier_threshold=self.config.bertopic_outlier_threshold,
                )
            else:
                embeddings = self.embedding_service.encode(
                    clustering_texts,
                    model_name=self.config.embedding_model,
                    local_model_path=self.config.embedding_local_path,
                )
                # PCA pre-reduction for K-means: 384 → 50 dims.
                # Improves cluster quality (fewer dimensions → less curse of dimensionality)
                # and speeds up clustering. The reduced embeddings are reused for scatter
                # projection so PCA runs only once per analysis.
                reduced_embeddings = embeddings
                if model_key == "kmeans":
                    try:
                        import numpy as np
                        from sklearn.decomposition import PCA as _PCA
                        _arr = np.asarray(embeddings)
                        if (
                            _arr.ndim == 2
                            and _arr.shape[0] >= 10
                            and _arr.shape[1] > 50
                        ):
                            _n_pca = min(50, _arr.shape[1], _arr.shape[0] - 1)
                            if _n_pca >= 2:
                                reduced_embeddings = _PCA(
                                    n_components=_n_pca, random_state=42
                                ).fit_transform(_arr)
                    except Exception:  # pragma: no cover - sklearn always present
                        pass

                if model_key == "kmeans":
                    kmeans_embeddings = reduced_embeddings
                    model_result = self.kmeans_service.run(
                        kmeans_embeddings,
                        requested_clusters=self.config.kmeans_clusters,
                        random_state=self.config.kmeans_random_state,
                    )
                elif model_key == "hdbscan":
                    model_result = self.hdbscan_service.run(
                        embeddings,
                        min_cluster_size=self.config.hdbscan_min_cluster_size,
                        min_samples=self.config.hdbscan_min_samples,
                        metric=self.config.hdbscan_metric,
                    )
                else:  # pragma: no cover - guarded by request validation
                    raise TopicAnalysisInputError(f"Unsupported analysis mode '{model_key}'.")

            warnings.extend(model_result.get("warnings", []))
            groups = self._build_groups(
                documents=prepared.documents,
                assignments=[int(value) for value in model_result.get("assignments", [])],
                explicit_groups=model_result.get("groups", {}),
                model_key=model_key,
            )
            # Let AI relabel first, then translate only whatever labels/examples still
            # need English display text. That avoids translating fresh AI labels back
            # through the normal output-translation pass.
            _, ai_warnings = self._apply_ai_labels(
                groups,
                model_key=model_key,
                text_column_name=text_column_name,
            )
            warnings.extend(ai_warnings)
            translated_group_count, translation_warnings = self._translate_group_outputs(groups)
            warnings.extend(translation_warnings)
            base_response["warnings"] = warnings
            base_response["translated_document_count"] = translated_group_count
            base_response["groups"] = groups
            if model_key == "kmeans" and embeddings is not None:
                base_response["scatter_points"] = self._build_scatter_points(
                    documents=prepared.documents,
                    assignments=[int(value) for value in model_result.get("assignments", [])],
                    embeddings=kmeans_embeddings,
                    groups=groups,
                )
            base_response["ok"] = True
            return base_response
        except (TopicAnalysisInputError, TopicAnalysisDependencyError) as exc:
            base_response["error"] = str(exc)
            return base_response
        except Exception as exc:  # pragma: no cover - defensive guard
            base_response["error"] = f"Analysis failed unexpectedly: {exc}"
            return base_response

    def _build_groups(
        self,
        *,
        documents: list[PreparedDocument],
        assignments: list[int],
        explicit_groups: dict[str, dict[str, object]],
        model_key: str,
    ) -> list[dict[str, object]]:
        """Map cluster assignments back to documents and build the serialisable group list with labels and examples."""
        grouped_documents: dict[int, list[PreparedDocument]] = defaultdict(list)
        for assignment, document in zip(assignments, documents):
            grouped_documents[int(assignment)].append(document)

        total_documents = max(1, len(documents))
        groups: list[dict[str, object]] = []
        ordered_group_ids = sorted(
            grouped_documents.keys(),
            key=lambda group_id: (-len(grouped_documents[group_id]), group_id),
        )

        fallback_prefix = "Topic" if model_key == "bertopic" else "Group"
        for group_id in ordered_group_ids:
            group_key = str(group_id)
            grouped_rows = grouped_documents[group_id]
            grouped_texts = [document.text for document in grouped_rows]
            explicit_group = explicit_groups.get(group_key, {})
            terms = [
                str(term)
                for term in explicit_group.get("terms", [])
                if isinstance(term, str) and term.strip()
            ]
            terms = self.keyword_service.sanitize_terms(terms, top_n=self.config.top_terms_per_group)
            if not terms:
                terms = self.keyword_service.top_terms(grouped_texts, top_n=self.config.top_terms_per_group)

            is_noise = bool(explicit_group.get("is_noise", group_id == -1))
            label = self.narrative_service.build_label(
                texts=grouped_texts,
                terms=terms,
                is_noise=is_noise,
                fallback_prefix=fallback_prefix,
                fallback_id=group_key,
                prefer_terms=model_key == "bertopic",
            )
            examples = self.representative_example_service.select(
                grouped_rows,
                terms=terms,
                max_examples=self.config.representative_examples_per_group,
            )
            comment = self.narrative_service.build_comment(
                label=label,
                count=int(len(grouped_rows)),
                total_documents=total_documents,
                examples=examples,
            )
            groups.append(
                {
                    "group_id": group_key,
                    "label": label,
                    "source_label": None,
                    "translated": False,
                    "ai_generated": False,
                    "comment": comment,
                    "count": int(len(grouped_rows)),
                    "share": round(len(grouped_rows) / total_documents, 4),
                    "total_documents": total_documents,
                    "terms": list(terms),
                    "examples": examples,
                    "is_noise": is_noise,
                    # Keep a lightweight row_number/text list for drilldown modals and
                    # fast filtered rebuilds without carrying the full document objects.
                    "_documents": [
                        {
                            "row_number": int(document.row_number),
                            "text": document.text,
                        }
                        for document in grouped_rows
                        if int(document.row_number) > 0 and document.text
                    ],
                }
            )

        if model_key == "bertopic":
            groups = self._translate_and_merge_bertopic_groups(groups)

        return groups

    def _translate_and_merge_bertopic_groups(
        self, groups: list[dict[str, object]]
    ) -> list[dict[str, object]]:
        """Translate BERTopic terms to English and merge topics that share the same first translated term.

        Merging handles multilingual datasets where the same concept appears as separate topics per language.
        """
        translation_service = self.text_preparation_service.translation_service

        all_terms: list[str] = []
        seen_terms: set[str] = set()
        for group in groups:
            if group.get("is_noise"):
                continue
            for term in group.get("terms", []):
                if term and term not in seen_terms:
                    seen_terms.add(term)
                    all_terms.append(term)

        term_to_english: dict[str, str] = {t: t for t in all_terms}
        if translation_service and all_terms:
            result = translation_service.translate(all_terms)
            for source, translated, was_translated in zip(all_terms, result.texts, result.translated_flags):
                if was_translated and translated.strip():
                    term_to_english[source] = translated.strip()

        for group in groups:
            if group.get("is_noise"):
                continue
            raw_terms = list(group.get("terms", []))
            translated_terms: list[str] = []
            seen: set[str] = set()
            for t in raw_terms:
                english = term_to_english.get(t, t)
                key = english.casefold()
                if key not in seen:
                    seen.add(key)
                    translated_terms.append(english)
            group["terms"] = translated_terms
            if translated_terms:
                new_label = " / ".join(t.replace("_", " ") for t in translated_terms[:2])
                if new_label != group.get("label"):
                    group["source_label"] = group["label"]
                    group["translated"] = True
                    group["label"] = new_label

        merge_into: dict[str, str] = {}
        first_term_index: dict[str, str] = {}
        for group in groups:
            if group.get("is_noise"):
                continue
            terms = group.get("terms", [])
            if not terms:
                continue
            key = terms[0].casefold().strip().rstrip("s")  # Strip trailing "s" to collapse simple plurals before comparing.
            gid = str(group["group_id"])
            if key in first_term_index:
                merge_into[gid] = first_term_index[key]
            else:
                first_term_index[key] = gid

        if merge_into:
            group_by_id = {str(g["group_id"]): g for g in groups}
            for src_id, tgt_id in merge_into.items():
                src = group_by_id[src_id]
                tgt = group_by_id[tgt_id]
                # Merge only the exported group payload; the raw assignments stay as-is
                # because this is a display-layer dedupe for multilingual topic names.
                tgt["_documents"].extend(src.get("_documents", []))
                tgt["count"] = int(tgt["count"]) + int(src["count"])
            merged_ids = set(merge_into.keys())
            groups = [g for g in groups if str(g["group_id"]) not in merged_ids]

        grand_total = max(1, sum(int(g["count"]) for g in groups))
        for group in groups:
            count = int(group["count"])
            group["share"] = round(count / grand_total, 4)
            group["total_documents"] = grand_total
            group["comment"] = self.narrative_service.build_comment(
                label=str(group["label"]),
                count=count,
                total_documents=grand_total,
                examples=group.get("examples", []),
            )

        return sorted(groups, key=lambda g: (-int(g["count"]), str(g["group_id"])))

    @staticmethod
    def _sample_group_texts(grouped_texts: list[str], *, limit: int) -> list[str]:
        unique_texts: list[str] = []
        seen: set[str] = set()
        for text in grouped_texts:
            key = text.casefold()
            if key in seen:
                continue
            seen.add(key)
            unique_texts.append(text)
            if len(unique_texts) >= limit:
                break
        return unique_texts

    def _apply_ai_labels(
        self,
        groups: list[dict[str, object]],
        *,
        model_key: str,
        text_column_name: str,
    ) -> tuple[int, list[str]]:
        if self.ai_label_service is None or not groups:
            return 0, []

        try:
            result = self.ai_label_service.label_groups(
                groups,
                model_key=model_key,
                text_column_name=text_column_name,
            )
        except Exception as exc:  # pragma: no cover - defensive guard
            logger.info("AI topic labeling failed unexpectedly: %s", exc)
            return 0, ["AI topic labeling was skipped and heuristic labels were kept."]

        relabeled_count = 0
        for group in groups:
            group_id = str(group.get("group_id", "")).strip()
            new_label = result.labels_by_group_id.get(group_id, "").strip()
            current_label = str(group.get("label", "")).strip()
            if not new_label or not current_label or new_label == current_label:
                continue

            group["source_label"] = current_label
            group["label"] = new_label
            group["translated"] = False
            group["ai_generated"] = True
            relabeled_count += 1

        for group in groups:
            count = int(group.get("count", 0))
            total_documents = max(1, int(group.get("total_documents", count)))
            group["comment"] = self.narrative_service.build_comment(
                label=str(group.get("label", "Group")),
                count=count,
                total_documents=total_documents,
                examples=[
                    example
                    for example in group.get("examples", [])
                    if isinstance(example, dict)
                ],
            )

        warnings = list(result.warnings)
        if relabeled_count:
            warnings.append(f"AI generated clearer labels for {relabeled_count} group(s).")
        return relabeled_count, warnings

    def _translate_group_outputs(self, groups: list[dict[str, object]]) -> tuple[int, list[str]]:
        translation_service = self.text_preparation_service.translation_service
        if translation_service is None or not groups:
            return 0, []

        warnings: list[str] = []
        translated_label_count = sum(1 for group in groups if bool(group.get("translated")))
        translated_example_count = 0
        for group in groups:
            warnings.extend(
                str(message)
                for message in group.pop("_label_translation_warnings", [])
                if isinstance(message, str) and message.strip()
            )

        untranslated_groups = [
            group
            for group in groups
            if not bool(group.get("translated")) and not bool(group.get("ai_generated"))
        ]
        if untranslated_groups:
            label_texts = [str(group.get("label", "")).strip() for group in untranslated_groups]
            label_result = translation_service.translate(label_texts)
            warnings.extend(label_result.warnings)
            for group, source_label, translated_label, translated_flag in zip(
                untranslated_groups,
                label_texts,
                label_result.texts,
                label_result.translated_flags,
            ):
                if translated_flag and translated_label.strip():
                    group["source_label"] = source_label
                    group["label"] = translated_label.strip()
                    group["translated"] = True
                    translated_label_count += 1
                else:
                    group["source_label"] = None
                    group["translated"] = False

        example_records: list[dict[str, object]] = []
        example_texts: list[str] = []
        for group in groups:
            for example in group.get("examples", []):
                if not isinstance(example, dict):
                    continue
                example_text = str(example.get("text", "")).strip()
                if not example_text:
                    continue
                example_records.append(example)
                example_texts.append(example_text)

        if example_texts:
            example_result = translation_service.translate(example_texts)
            warnings.extend(example_result.warnings)
            for example, source_text, translated_text, translated_flag in zip(
                example_records,
                example_texts,
                example_result.texts,
                example_result.translated_flags,
            ):
                if translated_flag and translated_text.strip():
                    example["source_text"] = source_text
                    example["text"] = translated_text.strip()
                    example["translated"] = True
                    translated_example_count += 1
                else:
                    example["source_text"] = None
                    example["translated"] = False

        for group in groups:
            count = int(group.get("count", 0))
            total_documents = max(1, int(group.get("total_documents", count)))
            group["comment"] = self.narrative_service.build_comment(
                label=str(group.get("label", "Group")),
                count=count,
                total_documents=total_documents,
                examples=[
                    example
                    for example in group.get("examples", [])
                    if isinstance(example, dict)
                ],
            )

        translated_count = translated_label_count + translated_example_count
        if translated_count:
            warnings.append(
                f"Translated {translated_label_count} group label(s) and {translated_example_count} representative response(s) to English for display after grouping."
            )
        return translated_count, warnings

    def _translate_ngram_buckets(self, buckets: list[dict[str, object]]) -> tuple[int, list[str]]:
        translation_service = self.text_preparation_service.translation_service
        if translation_service is None or not buckets:
            return 0, []

        warnings: list[str] = []
        items: list[dict[str, object]] = []
        texts: list[str] = []
        for bucket in buckets:
            for item in bucket.get("items", []):
                if not isinstance(item, dict):
                    continue
                term = str(item.get("term", "")).strip()
                if not term:
                    continue
                items.append(item)
                texts.append(term)

        if not texts:
            return 0, []

        translation_result = translation_service.translate(texts)
        warnings.extend(translation_result.warnings)

        translated_count = 0
        for item, source_term, translated_term, translated_flag in zip(
            items,
            texts,
            translation_result.texts,
            translation_result.translated_flags,
        ):
            cleaned_translation = self.keyword_service.sanitize_terms(
                [translated_term],
                top_n=1,
            )
            display_term = cleaned_translation[0] if cleaned_translation else translated_term.strip()
            if translated_flag and display_term:
                item["source_term"] = source_term
                item["term"] = display_term
                item["translated"] = True
                translated_count += 1
            else:
                item["source_term"] = None
                item["translated"] = False

        if translated_count:
            warnings.append(
                f"Translated {translated_count} common phrase(s) to English for display after analysis."
            )
        return translated_count, warnings

    def _build_scatter_points(
        self,
        *,
        documents: list[PreparedDocument],
        assignments: list[int],
        embeddings,
        groups: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        """Project PCA-reduced embeddings to 2D via a second PCA pass for scatter-plot visualisation."""
        if not documents or not assignments:
            return []

        try:
            import numpy as np
            from sklearn.decomposition import PCA
        except Exception as exc:  # pragma: no cover - dependency error path
            raise TopicAnalysisDependencyError(
                "scikit-learn and numpy are required for K-means scatter plots."
            ) from exc

        embedding_array = np.asarray(embeddings)
        if embedding_array.ndim != 2 or embedding_array.shape[0] == 0:
            return []

        if embedding_array.shape[1] > 2 and embedding_array.shape[0] >= 2:
            # Input may already be PCA-reduced to ~50 dims; PCA from 50→2 is ~7× faster
            # than from 384→2 because SVD cost scales with d².
            projected = PCA(n_components=2, random_state=self.config.kmeans_random_state).fit_transform(embedding_array)
        elif embedding_array.shape[1] == 2:
            projected = embedding_array
        elif embedding_array.shape[1] == 1:
            x_axis = embedding_array[:, 0]
            y_axis = np.zeros_like(x_axis)
            projected = np.column_stack((x_axis, y_axis))
        else:
            projected = np.zeros((embedding_array.shape[0], 2))

        group_labels = {
            str(group.get("group_id", "")): str(group.get("label", "Unlabelled group"))
            for group in groups
        }

        scatter_points: list[dict[str, object]] = []
        for index, (document, assignment) in enumerate(zip(documents, assignments)):
            group_key = str(int(assignment))
            scatter_points.append(
                {
                    "row_number": int(document.row_number),
                    "text": document.text,
                    "group_id": group_key,
                    "group_label": group_labels.get(group_key, "Unlabelled group"),
                    "x": float(projected[index][0]),
                    "y": float(projected[index][1]),
                }
            )

        return scatter_points
