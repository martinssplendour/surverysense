# Architecture

This repo uses a feature-first structure. Code should live with the product area it supports, and shared code should stay small.

## Backend Feature Ownership

Backend feature code lives under `backend/app/features`.

- `auth` owns login, logout, OAuth integration, authenticated user flow, and auth routes.
- `ingestion` owns CSV ingestion, encoding detection, manifest creation, cleaning, transformation, survey preparation, and upload routes.
- `analysis` owns topic analysis, embeddings, n-grams, community detection, AI topic labels, language detection, translation, and analysis routes.
- `results` owns stored result state, paging, filtering, result datasets, snapshots, and result data routes.
- `export` owns report generation, chart image decoding, and document/PDF/slide export services.
- `common` owns only small cross-feature interfaces or helpers that are genuinely shared.

Application assembly lives in `backend/app/application_setup.py`. It creates services and wires feature routers into the FastAPI app.

## Routes

Routes live inside the feature that owns the endpoint behavior:

- Auth routes: `backend/app/features/auth/routes.py`
- Upload/ingestion routes: `backend/app/features/ingestion/routes.py`
- Analysis routes: `backend/app/features/analysis/routes.py`
- Translation route: `backend/app/features/analysis/translation_routes.py`
- Result data routes: `backend/app/features/results/routes.py`

The composed workspace router lives at `backend/app/features/routes.py`. It should only assemble feature route modules and should not contain endpoint logic.

## Shared Code

Shared backend code is allowed in:

- `backend/app/core` for app-wide settings, auth helpers, and infrastructure-level concerns.
- `backend/app/models` for API/domain models used across feature boundaries.
- `backend/app/features/common` for small protocols, route context, and feature-facing shared helpers.

Do not add broad shared utility modules unless at least two features already need the same behavior. Prefer keeping code inside the owning feature.

## Tests

Backend tests mirror the feature layout:

- Auth tests: `backend/tests/features/auth`
- Ingestion tests: `backend/tests/features/ingestion`
- Analysis tests: `backend/tests/features/analysis`
- Results tests: `backend/tests/features/results`
- Export tests: `backend/tests/features/export`
- Cross-feature workflow tests: `backend/tests/integration`

Put narrow unit tests beside the feature they exercise. Put tests that verify multiple features working together in `backend/tests/integration`.
