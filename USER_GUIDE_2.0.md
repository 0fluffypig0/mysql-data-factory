# MySQL Data Factory 2.0 — User Guide

## Overview

MySQL Data Factory generates test data and inserts it into MySQL tables at scale. It works by taking a real record from your database as a template, then generating N copies with incremented primary keys and unique keys.

---

## Launching the GUI

```bash
python scripts/ui_app.py
```

On bastion host:

```batch
bin\run_gui.bat
```

The main window has 6 tabs. Work left to right.

---

## Tab 1: Connection

Configure your database connection.

| Field | Description |
|---|---|
| Host | MySQL server hostname or IP |
| Port | Default: 3306 |
| User | MySQL username |
| Password | MySQL password |
| Database | Target database name |

**Profiles**: Save and reload connection configurations using the "Save Profile" / "Load Profile" buttons. Profiles are stored in `config/connection_profiles.json` (excluded from git).

**Test Connection**: Verifies connectivity before proceeding.

**Connect**: Establishes a persistent session for the entire workflow.

---

## Tab 2: Scan

Scans the target database and caches metadata.

Click **Scan Database** to:
- Enumerate all tables
- Detect PKs, unique keys, JSON columns, auto-increment fields
- Identify marker columns (remark, source, created_by, etc.)
- Count rows and find MAX(pk) for each table
- Cache results to `metadata_cache/db_scan_<dbname>.json`

**Re-scan** is only needed if the schema has changed. Otherwise the cached result is reused automatically.

The table browser shows:
- Table name
- Row count
- Primary key column(s)
- Whether the table has a marker column

---

## Tab 3: Tasks

Configure which tables to insert into, and how many rows.

### Adding Tables

Click a table name in the list to configure it, then click **Add Task**.

### Per-Table Configuration

| Field | Description |
|---|---|
| Row Count | Number of rows to insert (1 to 10,000,000) |
| Batch Size | Rows per INSERT statement (default: 1,000) |
| Mode | `insert` / `dry-run` / `export` |
| Sample Method | How to pick the template row |
| PK Mode | How to determine the starting PK |

### Sample Method

| Method | When to use |
|---|---|
| `first_row` | Default — uses the first row in the table |
| `pk_lookup` | You know the exact PK value of the row to use as template |
| `where_clause` | You have a specific condition (e.g., `status = 'ACTIVE'`) |

**Important**: If the table has no rows, you cannot use it as a template. Insert at least one real row first.

### PK Mode

| Mode | When to use |
|---|---|
| `auto_increment_from_max` | Default — safe, always starts above current MAX |
| `fixed_start` | You need to start from a specific value regardless of MAX |
| `explicit_range` | You know both start and end PK |

**Warning**: `fixed_start` and `explicit_range` do **not** check for conflicts. Ensure the range is clear before using.

### Marker Column

If the table has a column like `remark`, `source`, or `created_by`, you can tag all inserted rows with a value (e.g., `"data_factory_test"`). This makes bulk cleanup easier.

### Execution Mode

| Mode | Effect |
|---|---|
| `insert` | Normal insertion |
| `dry-run` | Validates data generation and counts rows, but does not insert |
| `export` | Generates chunk CSV files only, no insertion |

### Task Templates

Save a multi-table task configuration for reuse:

1. Configure all tables
2. Click **Save Template** → enter a name
3. Next session: click **Load Template** → select the saved name

Templates are stored in `task_templates/` (excluded from git by default).

---

## Tab 4: Preview

Before executing, review a sample of the generated data.

- Shows the first few rows of each table's generated data
- Verifies PK sequencing, column values, and format
- If something looks wrong, go back to Tasks and adjust

**Preview does not insert data.**

---

## Tab 5: Execute

Click **Run Campaign** to start insertion.

### Progress Display

- Overall campaign progress bar
- Per-table detail: phase (sample / generate / insert), rows/s, ETA
- Chunk and batch counters
- Log window showing key events

### After Completion

- Results table shows per-table: status, rows inserted, PK range
- Paths to reports and cleanup SQL are shown at the bottom

### Stopping

The **Stop** button requests a graceful stop after the current batch completes.

---

## Tab 6: History

Browse all past campaigns and manage cleanup.

### Three Sub-Tabs

**Plans**: Lists all campaign plan files (campaign ID, database, status, time).

**Reports**: Lists all execution reports with full detail:
- Time, database, table name
- Mode (insert / dry-run / export)
- Rows inserted / attempted
- PK column and range
- Campaign ID
- Links to report file and cleanup SQL

Click any row to view full JSON detail in the bottom panel.

**Cleanup SQL**: Lists all generated cleanup SQL files. Click to view SQL in the detail panel.

### Running Cleanup

1. Click any report row → the campaign ID is auto-filled in the Cleanup field
2. Click **Dry Run** → preview what would be deleted (COUNT query, no deletion)
3. Click **Execute Cleanup** → opens a high-safety confirmation dialog

The confirmation dialog shows:
- Database and campaign ID
- Total tables and estimated row count
- Per-table: PK column, range, estimated rows, sample preview

Click the red **Delete** button to confirm. This is irreversible.

---

## CLI Reference

### Cleanup

```bash
# By PK range (dry-run)
python scripts/cleanup.py --env-file .env \
  --table TABLE --pk-column PK_COL \
  --pk-start START --pk-end END \
  --dry-run

# By PK range (execute)
python scripts/cleanup.py --env-file .env \
  --table TABLE --pk-column PK_COL \
  --pk-start START --pk-end END \
  --execute

# By campaign ID
python scripts/cleanup.py --env-file .env \
  --campaign-id CAMPAIGN_ID \
  --dry-run

# Generate SQL only (no DB access)
python scripts/cleanup.py --env-file .env \
  --table TABLE --pk-column PK_COL \
  --pk-start START --pk-end END \
  --sql-only
```

### Smoke Test

```bash
# Validate pipeline (no insert)
python scripts/smoke_test.py --env-file .env

# Validate + insert 10 rows
python scripts/smoke_test.py --env-file .env --insert --rows 10

# Target specific table
python scripts/smoke_test.py --env-file .env --table t_legal
```

### Pressure Test

```bash
python scripts/pressure_test_100k.py \
  --env-file .env \
  --table YOUR_TABLE \
  --rows 100000 \
  --batch-size 1000 \
  --chunk-size 5000
```

---

## Understanding Output Files

### Chunk CSV Files

Located in `data/output/<campaign_dir>/<table_dir>/`:

- `chunk_000001__rows_5000__range_200001__205000.csv`
- Each file contains one slice of the generated data
- Filename includes the PK range for easy reference

### Campaign Manifest

`campaign_manifest.json` — top-level evidence file:

```json
{
  "campaign_id": "a1b2c3d4",
  "db_name": "ji_test",
  "total_tables": 2,
  "total_rows_inserted": 110000,
  "tables": [...]
}
```

### Table Manifest

`table_manifest.json` — per-table evidence:

```json
{
  "table_name": "t_travel",
  "pk_columns": ["TRAVEL_ID"],
  "rows_inserted": 100000,
  "pk_range_start": "205001",
  "pk_range_end": "305000",
  "status": "completed"
}
```

### Campaign Summary CSV

`campaign_summary.csv` — spreadsheet-friendly summary of all tables in the campaign.

### Cleanup SQL

`sql/cleanup/cleanup_<campaign_id>.sql`:

```sql
-- Cleanup for campaign: a1b2c3d4
-- Table: t_travel
DELETE FROM `t_travel`
WHERE `TRAVEL_ID` >= '205001' AND `TRAVEL_ID` <= '305000';
```

---

## Language Switching

Use the **Language** menu (top-left) to switch between:

- 简体中文
- English
- 日本語

The selection is saved and restored on next launch.

---

## Tips

1. **Always dry-run first** on a new database to verify PK handling
2. **Use marker columns** to make cleanup easier (`remark = 'test_2026'`)
3. **Save task templates** if you will run the same tables repeatedly
4. **Use `explicit_range`** when testing a specific PK range on a staging database
5. **Check History before cleanup** to confirm the correct campaign ID
