# MySQL Data Factory 3.0.2 — User Guide

## Overview

MySQL Data Factory 3.0.2 generates append-only test data for real MySQL schemas by cloning a real row, incrementing PK and unique-key values, and inserting the generated rows in controlled batches.

The recommended release package is:

- project source code
- `env_export\mysql_factory_env.zip`

On the target bastion host, you unpack the project, run `bin\setup_offline.bat`, configure `.env`, and then use either the GUI or CLI wizard.

---

## Launching the GUI

Local development:

```bash
python scripts/ui_app.py
```

Offline / bastion host:

```batch
bin\run_gui.bat
```

The GUI is now based on `tkinter`, but the workflow stays the same: Connection → Scan → Tasks → Preview → Execute → History.

---

## Tab 1: Connection

Use this tab to define or load DB connection settings.

| Field | Meaning |
|---|---|
| Host | MySQL server IP or hostname |
| Port | MySQL port |
| User | account used for scan/insert/cleanup |
| Password | password for that account |
| Database | target schema |
| Charset | normally `utf8mb4` |

You can:

- load credentials from `.env`
- save named profiles locally
- test the connection before entering the main workflow
- establish a shared GUI session connection

---

## Tab 2: Scan

The scan step collects database metadata and caches it locally.

Detected metadata includes:

- columns and types
- primary keys
- unique keys
- JSON columns
- auto-increment columns
- time columns
- potential marker columns
- current row counts

Cache files are stored under `metadata_cache/` and can be reused across sessions.

---

## Tab 3: Tasks

This tab defines what to append.

Per-table options include:

| Setting | Meaning |
|---|---|
| Row Count | how many rows to generate |
| Batch Size | how many rows per insert batch |
| Sample Method | how to choose the template row |
| PK Mode | how to choose the target PK range |
| Mode | `insert`, `dry-run`, or `export` |
| Marker Column / Value | optional cleanup-friendly tag |

Supported sample methods:

- `first_row`
- `pk_lookup`
- `where_clause`

Supported PK modes:

- `auto_increment_from_max`
- `fixed_start`
- `explicit_range`

Task templates can be saved under `task_templates/` for repeated workflows.

---

## Tab 4: Preview

Preview shows a small set of generated rows before you commit to execution.

Use it to verify:

- PK sequencing
- field formats
- marker-column values
- sample-row suitability

This step is especially useful before large append jobs.

---

## Tab 5: Execute

When you run a campaign, the tool performs these steps for each table:

1. sample a source row
2. compute PK and unique-key start values
3. generate chunk CSV files
4. stream chunk files into batched inserts
5. write reports and manifests

The 3.0.2 implementation is designed to keep memory low by processing chunk files sequentially during insert.

Execution output includes:

- campaign progress
- per-table status
- inserted row counts
- failed batch counts
- PK range summary

---

## Tab 6: History

History lets you inspect:

- saved plans
- execution reports
- generated cleanup SQL

From this tab you can also run:

- cleanup dry-run
- real cleanup execution with confirmation dialog

Cleanup relies on the exact PK ranges recorded in the reports, so you do not need to reconstruct those ranges manually after a normal campaign.

---

## CLI Reference

### Connection Test

```bash
python scripts/test_connection.py --env-file .env
```

### Smoke Test

```bash
python scripts/smoke_test.py --env-file .env --table your_table --rows 5
python scripts/smoke_test.py --env-file .env --table your_table --rows 10 --insert
```

### Pressure Test

```bash
python scripts/pressure_test_100k.py \
  --env-file .env \
  --table your_table \
  --rows 100000 \
  --batch-size 500 \
  --chunk-size 5000
```

### Full Integration Validation

```bash
python scripts/test_v3_full.py --env-file .env
```

### Cleanup by Range

```bash
python scripts/cleanup.py --env-file .env \
  --table your_table \
  --pk-column ID \
  --pk-start 100001 \
  --pk-end 200000 \
  --dry-run
```

### Cleanup by Campaign ID

```bash
python scripts/cleanup.py --env-file .env --campaign-id YOUR_CAMPAIGN_ID --dry-run
```

---

## Output Artifacts

During execution the tool writes:

- chunk CSV files under `data/output/`
- campaign and table manifests under the campaign directory
- per-table JSON reports under `reports/`
- cleanup SQL under `sql/cleanup/`

These artifacts are what make later validation and cleanup safe.

---

## Operational Tips

1. Start with preview or dry-run when testing a new schema.
2. Use a marker column when the table offers one.
3. For weak bastion hosts, prefer conservative batch sizes first, then scale up.
4. Keep the project directory and runtime together after deployment.
5. Always confirm cleanup by dry-run before delete on shared environments.


