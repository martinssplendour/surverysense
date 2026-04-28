# Frontend Architecture

The frontend is plain HTML, CSS, and browser-side ES modules served by FastAPI from `frontend/`.

## CSS

`styles.css` is an import manifest only. The active CSS architecture is ownership-based:

- `styles/00-tokens.css`: design tokens
- `styles/01-base.css`: browser/base defaults
- `styles/02-layout.css`: shared page shell and workspace layout
- `styles/components/`: reusable UI surfaces
- `styles/features/`: screen or workflow-owned styles
- `styles/responsive.css`: shared responsive corrections that coordinate multiple surfaces

See `styles/README.md` for ownership rules. Do not add new numbered override/final/polish modules; put the rule in the owning component or feature file.

## JavaScript

`results.js` is the entry-point orchestrator. It should wire modules together and start the page runtime; product behavior belongs inside the feature folder that owns it.

Primary results domains:

- `results/analysis/`: analysis controls, requests, and result rendering
- `results/analysisGroupModal/`: representative-response modal behavior
- `results/charts/`: Plotly rendering support, chart export, and report preview/download
- `results/data/`: paginated row API/state/view helpers
- `results/events/`: DOM event binding that delegates to feature APIs
- `results/shared/`: elements, global state, constants, and pure utilities
- `results/workspace/`: workspace navigation, persistence, reset, preview table, and filter bar behavior

See `results/README.md` for ownership and dependency rules. The short version: keep top-level files as thin public facades, keep implementation inside the owning folder, and do not let `shared/` import feature modules.

When adding browser behavior, keep event binding, API calls, state mutation, and rendering separate once the feature grows past a few functions.

## Local Checks

From `frontend/`:

```bash
npm run lint -- --max-warnings=0
npm test
```

From the repo root:

```bash
python scripts/check_architecture.py
python scripts/smoke_frontend_static.py
```

The smoke test starts the FastAPI app locally, checks the login shell and redirect behavior, and recursively verifies CSS imports and ES module imports resolve.
