# MySQL Data Factory 3.0.2 — Quick Start

This is the shortest path from unpacked project to a real database append run.

---

## 1. Prepare the Project

Make sure the project contains:

- source code
- `env_export\mysql_factory_env.zip`

If you are on a bastion host, you do not need Conda, pip internet access, or a system Python install.

---

## 2. Install the Offline Runtime

From the project root on Windows:

```batch
bin\setup_offline.bat
```

This will:

- extract the bundled runtime into `runtime\mysql_factory_env\`
- install all pip dependencies from `vendor/`
- verify `python.exe`, `pymysql`, and `tkinter`

---

## 3. Configure Database Access

```batch
copy .env.example .env
```

Edit `.env` and fill in:

```ini
DB_HOST=your.db.host
DB_PORT=3306
DB_USER=your_user
DB_PASSWORD=your_password
DB_NAME=your_database
```

---

## 4. Verify Connectivity

```batch
bin\test_connection.bat
```

Expected result:

- connection succeeds
- target database is reachable
- table count is displayed

---

## 5. Choose an Entry Point

### GUI

```batch
bin\run_gui.bat
```

Workflow:

1. Connection
2. Scan
3. Tasks
4. Preview
5. Execute
6. History

### CLI Wizard

```batch
bin\run_wizard.bat
```

---

## 6. Small Validation Run

Preview only:

```bash
python scripts/smoke_test.py --env-file .env --table your_table --rows 5
```

Insert 10 rows:

```bash
python scripts/smoke_test.py --env-file .env --table your_table --rows 10 --insert
```

---

## 7. Pressure Test

```bash
python scripts/pressure_test_100k.py \
  --env-file .env \
  --table your_table \
  --rows 100000 \
  --batch-size 500 \
  --chunk-size 5000
```

For million-row testing, reuse the same script with `--rows 1000000` after you have confirmed cleanup strategy and target table safety.

---

## 8. Cleanup

Dry-run first:

```bash
python scripts/cleanup.py --env-file .env \
  --table your_table \
  --pk-column ID \
  --pk-start 100001 \
  --pk-end 200000 \
  --dry-run
```

Then execute:

```bash
python scripts/cleanup.py --env-file .env \
  --table your_table \
  --pk-column ID \
  --pk-start 100001 \
  --pk-end 200000 \
  --execute
```

You can also clean by campaign ID using the saved reports.

---

## Where the Runtime Lives

After setup, the project becomes self-contained:

```text
runtime\mysql_factory_env\python\python.exe
runtime\mysql_factory_env\vendor\
```

You can move the whole unpacked project directory on the same machine without needing a global Python install.

