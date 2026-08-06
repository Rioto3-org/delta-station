# Delta Station Agent Instructions

## Role

This repository is the implementation and design workspace for the Delta Station observation database system.

The active agent is responsible for keeping the project definition, architecture, data model, operations, and implementation aligned. Documentation is not treated as a collection of independent notes: it is an operational source of truth.

## Current Context

- GAS performs the time-sensitive observation collection.
- GAS collects observations every 15 minutes and buffers rows in Google Sheets and images in Google Drive.
- K3s runs the PostgreSQL importer once per day and stores the authoritative observations and image bytes in PostgreSQL.
- The repository working-tree `outputs/` directory is not the same storage as the K3s PVC.
- The PostgreSQL migration and manual GAS-to-PostgreSQL import verification are complete.
- The old SQLite data and Python scraper remain as historical/archive or disabled operational paths.
- The Streamlit dashboard still reads SQLite and is not yet a PostgreSQL consumer.

## Documentation Ownership

Before editing documentation, inspect the implementation, manifests, runtime configuration, and existing documents. Resolve contradictions instead of adding another competing explanation.

Keep these concerns separate:

- `README.md`: project purpose, current responsibilities, and shortest user entrypoint.
- `docs/ARCHITECTURE.md`: current system boundaries and data flow.
- `docs/DATA_MODEL.md`: schema, identifiers, constraints, image ownership, and migration rules.
- `docs/OPERATIONS.md`: K3s, PVC, Secrets, jobs, backups, monitoring, and recovery procedures.
- `docs/MIGRATION.md`: PostgreSQL migration decisions, stages, rollback, and validation.
- Historical or superseded documents: label them explicitly or move them to an archive when requested.

Do not describe a planned design as current operation. Every operational claim must be traceable to a manifest, command, code path, or verified runtime state.

## Design Responsibilities

The agent responsible for design must:

1. Define system boundaries and ownership before proposing implementation changes.
2. Keep ingestion, persistence, image storage, dashboard access, and backup responsibilities explicit.
3. Prefer one authoritative data path and document any buffer or cache separately.
4. Treat credentials, runtime data, PVC contents, and generated outputs as environment state, not source code.
5. Preserve idempotency and recovery behavior when changing ingestion or storage.
6. Evaluate PostgreSQL changes with schema, connection, authentication, image storage, backup, and rollback implications together.
7. Avoid introducing a new worker, API, storage service, or compatibility layer without explaining the operational need.

## Change Workflow

For a documentation or design task:

1. Inspect the current branch and working tree.
2. Read the relevant documents and implementation sources.
3. Verify current runtime behavior when the claim concerns production or K3s.
4. State contradictions and assumptions before making structural changes.
5. Make the smallest coherent document or design change.
6. Check links, commands, paths, schedules, and names against the repository.
7. Run the relevant tests or validation commands when practical.
8. Commit changes with a Conventional Commits message.

Do not rewrite documents merely to make them look consistent. Preserve historical context when it explains why the current design exists, but mark it as historical.

## Security and Data Rules

- Never commit service-account keys, `.env` files, database files, images, or other runtime secrets.
- Do not put host-specific mount paths in the logical data model.
- Keep source image URLs, logical storage identifiers, and image bytes as separate concepts.
- Do not delete buffered GAS/Drive data until database insertion and image persistence have been verified.
- Treat a failed or unverified import as recoverable; preserve the source buffer for retry.
