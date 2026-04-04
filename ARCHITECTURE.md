# MySQL Data Factory 2.0 — Architecture

## Overview

MySQL Data Factory is a local, offline-capable tool for generating and inserting test data into MySQL databases. It is designed around a **bastion host deployment model**: build and prepare data on an online machine, then execute on a machine with limited connectivity.

```
┌─────────────────────────────────────────────────────────────────┐
│                        User Interfaces                          │
│                                                                 │
│   GUI (PySide6)           CLI Wizard          Legacy CLI        │
│   scripts/ui_app.py      scripts/wizard.py    scripts/*.py      │
└────────────────┬────────────────┬──────────────────────────────┘
                 │                │
                 ▼                ▼
┌─────────────────────────────────────────────────────────────────┐
│                       Workflow Layer                            │
│                                                                 │
│         src/workflow/campaign_runner.py                         │
│         (orchestrates: sample → generate → insert → report)    │
└──────┬────────────┬──────────────┬──────────────────┬──────────┘
       │            │              │                  │
       ▼            ▼              ▼                  ▼
┌──────────┐ ┌──────────┐ ┌────────────┐ ┌──────────────────────┐
│  Sample  │ │ Generate │ │  Execute   │ │      Report          │
│ selector │ │   row    │ │  batch     │ │   history.py         │
│          │ │ builder  │ │  runner    │ │   cleanup_runner.py  │
└──────────┘ └──────────┘ └────────────┘ └──────────────────────┘
       │            │              │
       ▼            ▼              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Infrastructure Layer                        │
│                                                                 │
│   src/db/connection.py    src/metadata/scanner.py              │
│   src/config/app_config.py  src/strategy/pk_planner.py         │
└─────────────────────────────────────────────────────────────────┘
```

---

## Core Concepts

### Campaign

A **campaign** is the top-level execution unit. Each campaign:

- Has a unique `campaign_id` (e.g., `20260330_143022_a1b2c3`)
- Contains one or more **TaskItems** (one per table)
- Produces a named output directory under `data/output/`
- Generates a `campaign_manifest.json` and `campaign_summary.csv`
- Generates cleanup SQL in `sql/cleanup/`

### TaskItem

A **TaskItem** is the configuration for inserting data into one table:

| Field | Description |
|---|---|
| `table_name` | Target table |
| `row_count` | Number of rows to generate |
| `batch_size` | Rows per INSERT batch |
| `mode` | `insert` / `dry-run` / `export` |
| `sample_method` | How to pick the template record |
| `pk_config` | PK range strategy |
| `marker_column` | Optional column to tag inserted rows |
| `field_strategies` | Per-column overrides |

### Metadata Scan

Before any data can be generated, the tool scans the target database to collect:

- Column names, types, nullable flags
- Primary key columns
- Unique key columns
- JSON columns (handled specially)
- Auto-increment fields
- Candidate marker columns (remark, source, created_by, etc.)
- Row counts and current MAX(pk) values

Scan results are **cached** as JSON in `metadata_cache/`. No re-scan is needed between sessions.

### Sample Selection

The tool uses a real database record as a template for new rows. Three methods:

| Method | Description |
|---|---|
| `first_row` | Uses the first row from the table (default) |
| `pk_lookup` | Fetches a specific row by primary key |
| `where_clause` | Selects using a custom SQL WHERE clause |

### PK Range Planning

The tool must guarantee unique PKs across all inserted rows. Strategies:

| Mode | Description |
|---|---|
| `auto_increment_from_max` | Queries `MAX(pk) + 1` as the start (default) |
| `fixed_start` | Uses a user-specified start value |
| `explicit_range` | Uses a user-specified start and end |

Pattern support:
- Pure integers: `1`, `2`, `3`
- Zero-padded strings: `"00000001"`, `"00000002"`
- Prefix + number: `"KC0007"`, `"KC0008"`, `"AXC000000998"`

### Data Generation

Rows are generated from the template record by:

1. Incrementing PK and unique key columns by position
2. Copying all other columns verbatim
3. Applying per-column field strategy overrides if configured
4. Writing to chunk CSV files (default: 5,000 rows per chunk)

### Batch Insertion

Chunk CSV files are read and inserted in batches. Key design decisions:

- **Short-lived connections per batch** (default): Safe for bastion environments where connections time out
- **Shared connection mode** (GUI path): Uses a persistent connection for the entire campaign
- All batches use `executemany()` for efficiency
- JSON column values are re-validated before insertion

---

## Module Reference

### `src/config/`

| File | Purpose |
|---|---|
| `app_config.py` | `ConnectionConfig` (DB credentials), `AppPaths` (standard dirs), `.env` loading |

### `src/db/`

| File | Purpose |
|---|---|
| `connection.py` | `DatabaseManager`: connect/disconnect, query, execute, schema inspection |

### `src/metadata/`

| File | Purpose |
|---|---|
| `scanner.py` | `scan_database()`, `scan_table()`, `load_scan_result()`, `save_scan_result()` |
| `models.py` | `ColumnMetadata`, `TableMetadata`, `DatabaseScanResult` dataclasses |

### `src/sample/`

| File | Purpose |
|---|---|
| `selector.py` | `select_top_rows()`, `select_by_pk()`, `select_by_where()`, `normalize_sample_for_csv()` |

### `src/strategy/`

| File | Purpose |
|---|---|
| `pk_planner.py` | `PKRangeConfig`, `analyze_pk_pattern()`, `plan_pk_range()`, `increment_key_value()` |
| `field_strategy.py` | Per-column override strategies |

### `src/generate/`

| File | Purpose |
|---|---|
| `row_builder.py` | `generate_preview()`, `generate_to_chunks()`, `resolve_start_values()` |

### `src/execute/`

| File | Purpose |
|---|---|
| `batch_runner.py` | `insert_chunk_files()`, `BatchConfig`, `InsertionReport` |
| `cleanup_runner.py` | `execute_cleanup()`, `CleanupPlan`, `CleanupTarget` |
| `progress.py` | `ProgressSnapshot` (real-time progress tracking) |
| `preflight.py` | Pre-execution validation checks |

### `src/plan/`

| File | Purpose |
|---|---|
| `models.py` | `TaskItem`, `CampaignPlan` (JSON-serializable, file-persistent) |

### `src/report/`

| File | Purpose |
|---|---|
| `history.py` | `list_reports()`, `list_plans()`, `list_cleanup_sql()`, `load_report()` |

### `src/workflow/`

| File | Purpose |
|---|---|
| `campaign_runner.py` | `run_campaign()`: top-level orchestration, manifest writing, report saving |

### `src/ui/`

| File | Purpose |
|---|---|
| `main_window.py` | `MainWindow`: tab container, i18n menu, session signals |
| `session.py` | `SessionManager`: persistent DB connection for GUI |
| `page_connection.py` | Connection form, profile save/load |
| `page_scan.py` | Metadata scan trigger, table browser |
| `page_tasks.py` | Multi-table task configuration, template save/load |
| `page_preview.py` | Preview generated data before execution |
| `page_execute.py` | Campaign execution, real-time progress |
| `page_history.py` | History browser, cleanup dialog |
| `i18n.py` | Translation strings (zh_CN, en, ja) |

---

## Data Flow

```
User selects tables and row counts
           │
           ▼
campaign_runner.run_campaign()
           │
    ┌──────┴───────────────────────────────┐
    │  For each TaskItem:                  │
    │                                      │
    │  1. _get_sample()                    │
    │     → select_top_rows() / pk / where │
    │     → normalize_sample_for_csv()     │
    │                                      │
    │  2. resolve_start_values()           │
    │     → SELECT MAX(pk) FROM table      │
    │     → Apply pk_config overrides      │
    │                                      │
    │  3. generate_to_chunks()             │
    │     → For each row: increment PK     │
    │     → Write chunk_NNNNNN.csv files   │
    │                                      │
    │  4. insert_chunk_files()             │
    │     → Read CSV → executemany()       │
    │     → Per-batch commit               │
    │                                      │
    │  5. _write_table_manifest()          │
    │     → table_manifest.json            │
    └──────────────────────────────────────┘
           │
           ▼
    _write_campaign_manifest()
    _write_campaign_summary_csv()
    cleanup.save_sql()
    report.save()
```

---

## Output Directory Structure

Each campaign creates a named directory under `data/output/`:

```
data/output/
└── 20260402_143022_JST__a1b2c3__ji_test/     ← campaign dir
    ├── campaign_manifest.json                  ← campaign-level evidence
    ├── campaign_summary.csv                    ← tabular summary
    └── 01__t_travel__pk_TRAVEL_ID__rows_5000/ ← table dir
        ├── table_manifest.json                 ← table-level evidence
        ├── chunk_000001__rows_5000__range_200001__205000.csv
        ├── chunk_000002__rows_5000__range_205001__210000.csv
        └── ...
```

---

## Connection Model

The tool uses **explicit, short-lived connections** by design:

- Each batch of inserts opens, commits, and closes a connection
- This is safe for bastion hosts where long-lived connections are unstable
- The GUI uses a **shared persistent connection** (SessionManager) to avoid re-authentication on bastion hosts that require one-time credentials

---

## Cleanup Architecture

Every campaign generates:

1. `sql/cleanup/cleanup_<campaign_id>.sql` — Ready-to-run SQL
2. `reports/report_<campaign_id>_<table>.json` — Records PK ranges

The cleanup system:

- Uses `pk_range_start` and `pk_range_end` from reports
- Optionally adds marker column filter as a safety net
- Provides dry-run (COUNT only) before actual deletion
- The GUI shows a high-safety confirmation dialog with all affected tables and estimated row counts
