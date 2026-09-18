# Reconciliation modules

`modules/` contains only real reconciliation engines used by ReconcileHub.
Demo/example reconciliations should not be registered in production.

## Add a new reconciliation

1. Create `modules/<module_id>/engine.py`.
2. Implement `BaseReconciliationModule` from `modules/base.py`.
3. Define a unique manifest id, required files and RBAC scopes.
4. Register the module in `modules/registry.py` with `module_registry.register(...)` (or in `ModuleRegistry.__init__` for a built-in module).
5. Grant the new scopes to the intended roles in `utils/permissions.py`.
6. Add a specialized React workspace only when that reconciliation needs its own UI.

The Modules screen reads `GET /api/modules` from FastAPI, so a registered module automatically appears in the module registry for users who have at least one required permission.

## Contract

Every module provides:

- `manifest` — metadata, permissions and file inputs;
- `validate_inputs()` — validation before execution;
- `run()` — reconciliation engine;
- `get_analytics()` — module-specific analytics contract;
- `export()` — optional module export implementation.

The universal endpoint is `POST /api/modules/{module_id}/run`. The platform handles RBAC and audit logging before and after the module execution.
