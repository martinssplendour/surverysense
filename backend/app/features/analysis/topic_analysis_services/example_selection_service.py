from __future__ import annotations

from app.features.analysis.topic_analysis_services.config import PreparedDocument
from app.features.analysis.topic_analysis_services.contracts import AnalysisExampleRecord


class RepresentativeExampleSelectionService:
    def select(
        self,
        documents: list[PreparedDocument],
        *,
        terms: list[str],
        max_examples: int,
    ) -> list[AnalysisExampleRecord]:
        if not documents:
            return []

        lower_terms = [term.casefold() for term in terms if term]
        scored_documents: list[tuple[tuple[float, float, int], PreparedDocument]] = []
        for document in documents:
            lowered = document.text.casefold()
            term_hits = sum(1 for term in lower_terms if term in lowered)
            length_target = abs(len(document.text) - 220)
            score = (float(term_hits), -float(length_target), -document.row_number)
            scored_documents.append((score, document))

        scored_documents.sort(key=lambda item: item[0], reverse=True)
        examples: list[AnalysisExampleRecord] = []
        seen_texts: set[str] = set()
        for _, document in scored_documents:
            dedupe_key = document.text.casefold()
            if dedupe_key in seen_texts:
                continue
            seen_texts.add(dedupe_key)
            examples.append(
                AnalysisExampleRecord(
                    row_number=int(document.row_number),
                    text=document.text,
                )
            )
            if len(examples) >= max_examples:
                break
        return examples
