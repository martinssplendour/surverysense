# CSS Architecture

`../styles.css` is the only CSS file imported by HTML. It is an import manifest; add rules in the owning module below instead of adding declarations directly to the manifest.

## Layers

- `00-tokens.css`: design tokens and custom properties.
- `01-base.css`: browser resets, base element rules, and global low-level defaults.
- `02-layout.css`: shared page shell and workspace layout primitives.
- `components/`: reusable UI surfaces that can appear in more than one workflow.
- `features/`: screen or workflow-owned styles.
- `responsive.css`: shared viewport corrections. Prefer putting responsive rules beside their owning feature unless the rule coordinates multiple surfaces.

The manifest imports component and feature files into two app layers: `app-base` before shared responsive rules, and `app-post-responsive` for modules that intentionally refine the dense results/data/header surfaces. Do not create late "final", "override", or "polish" files; move the rule to the owning component or feature instead.

## Ownership

- Upload screen rules: `features/upload.css`.
- Login/auth rules: `features/auth.css`.
- Dashboard rules: `features/dashboard.css`.
- Analysis setup rules: `features/analysis-setup.css`.
- Workspace shell/state rules: `features/workspace.css`.
- Data table and data workspace rules: `features/data-table.css` and `features/data-workspace.css`.
- Analysis result page rules: `features/analysis-results.css`, `features/analysis-results-layout.css`, and analysis components in `components/analysis-*.css`.
- Header rules: `components/app-header.css`.
- Export menu rules: `components/data-export-menu.css`.

When a selector is scoped to a body workspace state, keep it with the screen it adjusts unless it coordinates shell-level visibility or layout across multiple workspaces.
