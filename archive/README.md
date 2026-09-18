# Archive

This directory is intentionally outside the active ReconcileHub runtime.

Use it only for old implementations or completed migration documents that may be
useful as historical reference. Production code must not import anything from here.

Current archive:

- `legacy_streamlit/` — retired Streamlit interface;
- `legacy_docs/` — completed/outdated architecture migration notes.

Generated artifacts such as `dist/`, ZIP builds, databases, caches and compiled
Python files should **not** be archived here; they should simply stay out of Git.
