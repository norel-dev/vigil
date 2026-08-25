# DataPlatform — codebase report (pointer)

## Commit

- Repository root: `/Users/norel/dataplatform`, branch `feature/table-primary-keys-ui`,
  HEAD `7e30d98` ("State a key column's NOT NULL as a fact instead of a greyed-out toggle").

## Why this file is a pointer

The explorer has been run from both `app/backend` and `app/frontend` as its working
directory, so two knowledge paths exist. Keeping two full reports means keeping two
reports in sync, and they drift. **The canonical report lives at:**

`/Users/norel/dataplatform/app/backend/agent-knowledge/repository-explorer/CODEBASE.MD`

It covers the whole repository — the FastAPI backend under `app/backend/` and the
React/Vite console under `app/frontend/` — and is the one to read and the one to update.
