# Deployment Guide

This document describes the minimal closed loop only:

1. Build an offline environment on an online machine
2. Deploy it on a bastion host
3. Connect to MySQL with `.env`
4. Export `sample.csv`
5. Manually edit `template.csv`
6. Expand to `generated.csv`
7. Run `dry-run`
8. Batch insert

Notebook is not the main entry.

---

## 1. Online Machine: Build the Offline Environment

### Prerequisites

- Windows machine with internet access
- Conda available in `PATH`
- This repository checked out locally

### Command

```powershell
python scripts\build_offline_env.py
```

Optional rebuild:

```powershell
python scripts\build_offline_env.py --rebuild
```

### Output

```text
env_export\mysql_factory_env.tar.gz
```

This package contains only the minimal runtime needed for:

- `.env` loading
- MySQL connection
- CSV export
- CSV expansion
- JSON column validation
- dry-run
- batch insert

It also includes common bastion-host data-processing packages:

- `pandas`
- `numpy`
- `sqlalchemy`
- `openpyxl`
- `pyarrow`
- `tabulate`
- `tqdm`
- `python-dateutil`
- `ipython`

It does not package Jupyter as a first-class dependency anymore.

---

## 2. Bastion Host: Deploy the Offline Environment

### Copy the Repository

Copy the whole repository to the bastion host, including:

```text
mysql-data-factory\
├── env_export\
│   └── mysql_factory_env.tar.gz
├── bin\
├── scripts\
├── src\
├── .env.example
├── README.md
└── DEPLOYMENT.md
```

### Run Setup

```batch
cd /d D:\deploy\mysql-data-factory
bin\setup_offline.bat
```

What `bin\setup_offline.bat` does:

1. Checks `env_export\mysql_factory_env.tar.gz`
2. Extracts it to `C:\tools\mysql_factory_env`
3. Runs `conda-unpack`
4. Verifies `python.exe`

If setup succeeds, continue with `.env`.

---

## 3. Configure `.env`

### Create the File

```batch
copy .env.example .env
notepad .env
```

### Minimum Required Keys

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

### Optional Keys

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

Notes:

- `PRIMARY_KEY_COLUMNS` is required
- `UNIQUE_KEY_COLUMNS` is optional and should include only the columns that must be incremented
- `TIME_OFFSET_COLUMNS` is optional
- `JSON_COLUMNS` is optional and should list MySQL JSON columns preserved as JSON strings in CSV
- `CSV_BASE_DIR` defaults to `data`

---

## 4. Step 1: Test Connectivity

```batch
bin\test_connection.bat
```

What it checks:

- `.env` can be loaded
- Database connection succeeds
- `SELECT 1` succeeds
- `TARGET_TABLE` exists, if configured

---

## 5. Step 2: Export `sample.csv`

### Command

```batch
bin\export_sample.bat --table your_table --limit 3
```

If `--table` is omitted, the script uses `TARGET_TABLE`.

### Output Path

Default output:

```text
data\your_table\sample.csv
```

This first version only does:

```sql
SELECT * FROM your_table LIMIT N
```

No complex query builder is included.

---

## 6. Step 3: Manually Create `template.csv`

Open:

```text
data\your_table\sample.csv
```

Manually edit the rows you want to use as a template, then save as:

```text
data\your_table\template.csv
```

This is intentionally manual in the first version.

---

## 7. Step 4: Expand to `generated.csv`

### Command

```batch
bin\expand_rows.bat --table your_table --rows 100
```

Default input:

```text
data\your_table\template.csv
```

Default output:

```text
data\your_table\generated.csv
```

### First-Version Expansion Rules

- Primary key columns: increment from the starting value
- Required unique key columns: increment by sequence or suffix
- Time columns: increment by fixed day/second offset
- All other columns: copied as-is

This script does not:

- infer business rules
- use faker
- generate random values

---

## 8. Step 5: Run `dry-run`

### Command

```batch
bin\insert_csv.bat --table your_table --dry-run
```

Default input:

```text
data\your_table\generated.csv
```

### `dry-run` Output

At minimum it prints:

- target table
- CSV path
- total record count
- column names
- batch size
- primary key columns
- empty primary key row count
- duplicate primary key row count inside the CSV
- JSON columns
- invalid JSON row count
- invalid JSON example rows, if any

If `dry-run` fails, fix the CSV before inserting.

---

## 9. Step 6: Batch Insert

### Command

```batch
bin\insert_csv.bat --table your_table --batch-size 500
```

If `--batch-size` is omitted, the script uses `INSERT_BATCH_SIZE` from `.env`.

This first version does:

- plain `INSERT`
- batch insert

This first version does not do:

- upsert
- update
- delete

---

## 10. Recommended End-to-End Order

```text
1. python scripts\build_offline_env.py
2. copy repository + env_export to bastion host
3. bin\setup_offline.bat
4. copy .env.example .env
5. edit .env
6. bin\test_connection.bat
7. bin\export_sample.bat --table your_table --limit 3
8. manually save template.csv
9. bin\expand_rows.bat --table your_table --rows 100
10. bin\insert_csv.bat --table your_table --dry-run
11. bin\insert_csv.bat --table your_table --batch-size 500
```

---

## 11. Known Limits

- Single table only
- CSV only, with optional MySQL JSON column support
- Notebook is reference only
- No faker or random data generation
- No multi-table logic
- No foreign-key orchestration
- No upsert / update / delete
- No generic workflow engine
