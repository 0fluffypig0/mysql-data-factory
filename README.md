# MySQL Data Factory

Minimal single-table CSV workflow for an offline/bastion-host MySQL insert flow.

## Scope

This repository now focuses on one closed loop only:

1. Build an offline Python environment on an online machine
2. Deploy that environment on a bastion host
3. Read `.env` and connect to MySQL
4. Export a small sample from one table to `sample.csv`
5. Manually edit the CSV into `template.csv`
6. Expand the template into `generated.csv`
7. Run `dry-run`
8. Batch insert into the same table

Notebook is kept only as a reference/debug artifact. It is not the main entry.
Within this CSV workflow, MySQL `JSON` columns are supported via `JSON_COLUMNS`.

## Main Entry Scripts

- `python scripts\build_offline_env.py`
- `bin\setup_offline.bat`
- `bin\test_connection.bat`
- `bin\export_sample.bat`
- `bin\expand_rows.bat`
- `bin\insert_csv.bat`

## Required `.env` Keys

```env
DB_HOST=127.0.0.1
DB_PORT=3306
DB_USER=your_user
DB_PASSWORD=your_password
DB_NAME=your_database
DB_CHARSET=utf8mb4
TARGET_TABLE=your_table
PRIMARY_KEY_COLUMNS=id
```

Optional keys:

```env
UNIQUE_KEY_COLUMNS=
TIME_OFFSET_COLUMNS=
JSON_COLUMNS=
TIME_OFFSET_DAYS=0
TIME_OFFSET_SECONDS=0
EXPORT_SAMPLE_LIMIT=3
INSERT_BATCH_SIZE=500
CSV_BASE_DIR=data
```

## Quick Start

### 1. Build the offline environment on an online machine

```powershell
python scripts\build_offline_env.py
```

This creates:

```text
env_export\mysql_factory_env.tar.gz
```

### 2. Copy the repository to the bastion host

Copy the whole repository folder, including `env_export\mysql_factory_env.tar.gz`.

### 3. Deploy the offline environment on the bastion host

```batch
bin\setup_offline.bat
```

### 4. Prepare `.env`

```batch
copy .env.example .env
notepad .env
```

### 5. Test connectivity

```batch
bin\test_connection.bat
```

### 6. Export a sample CSV

```batch
bin\export_sample.bat --table your_table --limit 3
```

Default output:

```text
data\your_table\sample.csv
```

### 7. Edit the sample into a template

Manually edit:

```text
data\your_table\sample.csv
```

Save the edited file as:

```text
data\your_table\template.csv
```

### 8. Expand the template into generated rows

```batch
bin\expand_rows.bat --table your_table --rows 100
```

Default output:

```text
data\your_table\generated.csv
```

### 9. Run dry-run

```batch
bin\insert_csv.bat --table your_table --dry-run
```

`dry-run` also validates configured and detected MySQL JSON columns row by row.

### 10. Insert rows

```batch
bin\insert_csv.bat --table your_table --batch-size 500
```

## What This First Version Does Not Do

- No faker or random data generation
- No JSON or JSONL file workflow
- No wizard or GUI
- No multi-table workflows
- No upsert, update, or delete
- No foreign-key orchestration
- No business-rule inference beyond configured key/time columns

## More Detail

See `DEPLOYMENT.md` for the full offline deployment and CSV workflow steps.
