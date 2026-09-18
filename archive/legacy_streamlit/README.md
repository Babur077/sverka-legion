# Legacy Streamlit archive

This folder contains the original Streamlit UI kept only as historical reference.

The current ReconcileHub application is:

- React/Vite frontend in `src/`;
- FastAPI backend in `api.py`;
- reconciliation modules in `modules/`;
- shared backend code in `core/` and `utils/`.

Files in this folder are **not part of the production runtime**, are not imported by
the current application, and are not expected to stay runnable as the active codebase
evolves.

Do not add new product functionality here. If an old implementation is useful, port
the relevant logic into the active architecture instead of importing legacy UI code.
