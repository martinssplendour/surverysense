# Results Frontend Boundaries

`frontend/results.js` is the results page entry point. It should compose the feature modules, pass callbacks between them, and start the page runtime. Product behavior belongs in the feature module that owns it.

## Ownership

- `analysis/`: analysis controls, request orchestration, analysis result rendering, and analysis-specific UI state.
- `analysisGroupModal/`: response/document modal API calls, modal state, and modal rendering.
- `charts/`: Plotly chart export, report preview/download, generated chart images, and chart export metadata.
- `data/`: paginated row API calls, loaded row datasets, preview dataset state, and table-loading helpers.
- `events/`: DOM event binding only. Event modules should delegate to public feature APIs instead of owning business logic.
- `shared/`: DOM element lookup, global results state, constants, and pure formatting/escaping helpers. Shared modules must not import feature modules.
- `workspace/`: page-level workspace navigation, persistence, reset behavior, preview table rendering, filter bar rendering, and workspace visibility.

## Public Entry Points

These modules are intentionally imported across domain boundaries:

- `../results.js`: page entry point. Composes domains, configures callbacks, and starts the runtime.
- `analysis.js`: public analysis facade over `analysis/*`.
- `charts.js`: public charts facade over `charts/controller.js`.
- `charts/export.js`: public report-export facade over `charts/export/*`.
- `data/rows.js`: public data-table API. Owns row loading orchestration and re-exports narrow row view helpers.
- `dataExport.js`: public data-export facade over `data/export.js`.
- `filters.js`: public metadata-filter facade over `workspace/filters.js`.
- `columnRoles.js`: public column-role facade over `data/columnRoles.js`.
- `modals.js`: public analysis drilldown modal facade over `analysisGroupModal/*`.
- `resultsEventBindings.js`: public event-binding entry point over `events/*`.
- `shared.js`: public shared facade over constants, elements, and global results state.
- `workspace/workspace.js`: public workspace facade over `workspace/*`.

Keep facade files as re-export/configuration surfaces only. If a public module needs implementation, put that implementation in the owning folder and expose only the smallest stable API through the facade.

The architecture checker enforces this: new implementation files should not be added directly under `results/`. Top-level `*.test.js` files are allowed for page-level and facade coverage.

## Dependency Direction

- `frontend/results.js` may import public entry points and pass callbacks between domains.
- Feature modules may import `shared/`, `shared.js`, and their own folder.
- Cross-feature imports should prefer public facades or configured callbacks. Avoid reaching into another feature's private implementation file.
- `events/` may import public feature APIs because it is the event wiring layer.
- `shared/` must stay below every feature: no imports from `analysis/`, `charts/`, `data/`, `events/`, `workspace/`, or modal modules.

When a change needs a new cross-feature interaction, add the behavior to the owning feature first, then expose the smallest public function needed by the caller.

## Where New Code Goes

- New analysis request or rendering behavior goes in `analysis/`.
- New chart orchestration goes in `charts/controller.js`, renderers go in `charts/renderers/`, and report/chart export behavior goes in `charts/` or `charts/export/`.
- New row loading, pagination, or preview dataset behavior goes in `data/`.
- New cleaned-data export behavior goes in `data/export.js`.
- New column-role behavior goes in `data/columnRoles.js`.
- New filter behavior goes in `workspace/filters.js`.
- New workspace restore/reset/navigation behavior goes in `workspace/`.
- New event listeners go in `events/`, with the actual behavior delegated to the owning feature.
- New formatting helpers go in `shared/utils.js` only when they are pure and useful across more than one domain.
