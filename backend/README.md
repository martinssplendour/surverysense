# Verbatim App Backend

## Install

```bash
pip install -r requirements.txt
```

## Run

```bash
uvicorn app.main:app --reload
```

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

## Tests

```bash
python -m unittest tests.test_transformation_service tests.test_survey_preparation_services
```
