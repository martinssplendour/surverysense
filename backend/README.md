# Verbatim App Backend

## Install

```bash
pip install -r requirements.txt
```

## Run

```bash
uvicorn app.main:app --reload
```

The analysis pipeline now groups raw verbatim responses first, using multilingual embeddings by default. When translation is enabled, only output labels and representative examples are translated to English for display after grouping.

## Endpoint

- `POST /upload-ingest`

Upload a CSV file as multipart form data using the field name `file`.

The architect returns a manifest that distinguishes:

- `metadata_indices`
- `verbatim_indices` for wide files
- `vertical_assembly` for vertical files:
  - `record_key_indices`
  - `question_header_indices` in fallback order
  - `answer_col_idx`
  - `helper_indices`
  - `duplicate_resolution`
  - `row_consolidation`

## Data Preparation Services

The Verbatim App includes standalone survey cleaning/preparation services in `app/services/survey_preparation_services.py`, including:

- `UserIdCastingService`
- `FullTitleFallbackService`
- `MainTitleFallbackService`
- `TitleNormalizationColumnsService`
- `WideSurveyPivotService`
- `QuestionRecordExtractionService`
- `QuestionSelectionService`
- `QuestionTextService`
- `AnswerCoverageService`
- `CountryFilterService`
- `CareerMetadataBackfillService`

The ingestion pipeline also uses standalone vertical verbatim assembly services in `app/services/cleaning_services.py`, including:

- `TextNormalizationService`
- `NullScrubbingService`
- `QuestionHeaderResolutionService`
- `VerbatimHeaderCleaningService`
- `VerbatimQuestionSelectionService`
- `VerticalRecordFilterService`
- `DuplicateAnswerResolutionService`
- `MetadataConsolidationService`
- `VerticalRecordAssemblyService`
- `VerbatimRowFilterService`

## Gemini

Set `GEMINI_API_KEY` to enable the LLM architect. If the key is missing or Gemini fails, the backend falls back to a heuristic manifest generator.

Environment variables can be placed in [`.env.example`](C:/Users/HP/Downloads/tvp-analysis-main/Verbatim%20App/backend/.env.example) format as `Verbatim App/backend/.env`. The backend now auto-loads that file on startup when `python-dotenv` is installed.

## Translation

Analysis-time translation is controlled with:

- `TOPIC_TRANSLATION_ENABLED`
- `TOPIC_TRANSLATION_SOURCE_LANGUAGE`
- `TOPIC_TRANSLATION_TARGET_LANGUAGE`
- `TOPIC_TRANSLATION_BATCH_SIZE`

The current translation path uses `deep-translator` with Google Translate. It does not download a local model, but it does send translated output snippets to Google's translation service when analysis runs.

## AI Topic Labels

When `GEMINI_API_KEY` is configured and `TOPIC_AI_LABELING_ENABLED=true`, grouped analysis can make one batched Gemini call after clustering to replace weak heuristic labels with shorter human-readable English labels.

Latency controls:

- `TOPIC_AI_LABELING_TIMEOUT_SECONDS`
- `TOPIC_AI_LABELING_MAX_GROUPS`
- `TOPIC_AI_LABELING_MAX_EXAMPLES`
- `TOPIC_AI_LABELING_MAX_TERMS`
- `TOPIC_AI_LABELING_MAX_CHARS_PER_EXAMPLE`

The AI labeler does not decide group membership. It only renames the largest non-noise groups after clustering, and if the call fails or times out the backend keeps the heuristic labels.

## BERTopic Outliers

BERTopic can leave some clear responses in its `-1` outlier bucket. This backend can reassign those responses to the nearest existing theme after clustering.

- `TOPIC_BERTOPIC_REDUCE_OUTLIERS`
- `TOPIC_BERTOPIC_OUTLIER_THRESHOLD`

The current implementation uses BERTopic's embedding-based outlier reduction. With the default threshold `0.0`, outlier responses are assigned to their nearest existing theme whenever possible. Any responses that still remain in the `-1` bucket are shown as `Unassigned responses`.

## Tests

```bash
python -m unittest tests.test_transformation_service tests.test_survey_preparation_services
```
