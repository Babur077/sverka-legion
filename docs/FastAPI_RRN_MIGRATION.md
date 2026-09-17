# FastAPI migration — Bank RRN

## Current target

Keep the existing Bank RRN business rules intact while moving the source of truth for reconciliation execution to the backend.

## Migration stages

1. Backend module uses the existing `core.recon_engine.run_rrn_reconciliation`.
2. FastAPI `/api/modules/bank_rrn/run` returns the rich RRN result in a stable module-specific payload.
3. React switches from the browser `reconEngine` worker to the FastAPI endpoint.
4. Archive and audit become backend-owned persistence.
5. Browser `localStorage` remains only for lightweight UI preferences/draft metadata during the transition, then is removed as a source of business data.

## Compatibility rule

Do not simplify or rewrite RRN matching, reversals, duplicate handling, amount mismatches, unbinding, commissions, terminal summaries, or detected periods during the migration. Backend output should represent the behavior already implemented in `core/recon_engine.py`.
