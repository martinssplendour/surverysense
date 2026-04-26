# Verbatim App Demo Deck

Source baseline: Friday April 17, 2026 (`91a7e58`)
Source current snapshot: Monday April 20, 2026 (`e0477d7`)

## Slide 1

**Verbatim App: Repo, Data Pipeline, and Demo Story**

- Focus: data ingestion and cleaning, live demo flow, April 17 baseline, and April 20 improvements.
- Current runtime snapshot: `1` Render web service, `85` backend app modules, `68` backend service modules, `39` frontend JS modules.

## Slide 2

**Data Ingestion and Cleaning**

- Read upload: detect encoding, parse CSV safely, and create preview versus architect samples.
- Diagnose layout: wide versus vertical survey shape, using Gemini or rule-based heuristics.
- Transform deterministically: apply the manifest, clean headers, scrub null-like values, and enforce row limits.
- Build analysis dataset: keep metadata filterable, consolidate multipart verbatims, and select true open-text columns.
- Store and reuse: keep the result in memory for paging, filtering, reruns, representative examples, and export.

Why the engineering is justified:

- Survey exports arrive in multiple layouts, not one standard table.
- Identifier columns, scores, and fixed-response text must not be treated as open text.
- Multipart questions and duplicate answers need deterministic consolidation.
- The output has to support interactive filtering and export, not only one-off analysis.

Test-covered messy-data cases:

- Vertical pivots
- Multipart word slots
- UUID response ids
- Duplicate answer resolution
- Fixed-response rejection
- Metadata detection

## Slide 3

**Demo Flow**

1. Upload a messy CSV and show row count, encoding, and preview rows.
2. Open the manifest and call out wide versus vertical diagnosis plus metadata / verbatim detection.
3. Show the transformed table to prove the cleaning path.
4. Apply metadata filters to show filtered data and rerun behavior.
5. Run BERTopic or K-means and open representative documents.
6. Export PDF or Slides to show the workflow is end-to-end.

Live emphasis:

- Same uploaded file -> raw sample -> transformed analysis frame -> filtered rerun -> export artifact.

## Slide 4

**Repo Structure on Friday, April 17, 2026**

Runtime and structure:

- `1` runtime web service
- `45` backend app modules
- `34` backend service modules across `4` service packages
- `2` API modules
- `16` frontend JS modules
- `12` results-page JS modules
- `12` backend test modules

Architecture:

- Static frontend served by FastAPI.
- `routes_ingest.py` handled upload, analysis, export, paging, and translation.
- Core domains already existed: architect, cleaning / transformation, topic analysis, export, result storage.
- Uploaded results were held in memory; there was no durable database.

State and code shape:

- `routes_ingest.py`: `472` lines
- `workspace.js`: `682` lines
- `charts.js`: `593` lines
- `analysis.js`: `352` lines
- State and orchestration existed, but they were spread across larger mixed-responsibility files.

## Slide 5

**Improvements Between Friday April 17 and Monday April 20, 2026**

Comparison:

| Metric | Friday | Today |
| --- | --- | --- |
| Runtime web services | 1 | 1 |
| Backend app modules | 45 | 85 |
| Backend service modules | 34 in 4 packages | 68 in 5 packages |
| API modules | 2 | 7 |
| Frontend JS modules | 16 | 39 |
| Results JS modules | 12 | 34 |
| Backend test modules | 12 | 13 |

Important framing:

- Module count increased because responsibilities were decomposed into smaller units.
- The deployed system did **not** add more runtime services.

Refactor wins:

- `routes_ingest.py`: `472 -> 50` lines after route registration was split.
- `report_export_service.py`: `824 -> 141` lines after builder extraction for PDF, DOCX, and PPTX.
- `topic_analysis_service.py`: `690 -> 255` lines after contracts and execution helpers were extracted.
- `main.py`: `267 -> 64` lines after application wiring moved into `application_setup.py`.
- `workspace.js`: `682 -> 28`
- `charts.js`: `593 -> 72`
- `analysis.js`: `352 -> 19`

State and architecture now:

- App wiring is explicit in `application_setup.py`.
- Ingest routes are split into upload, analysis, result, and translation modules with shared context.
- Results-page state is explicit in `frontend/results/state.js`.
- Workspace, persistence, chart, and analysis behavior are split into focused modules.
