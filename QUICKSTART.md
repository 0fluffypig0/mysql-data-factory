# MySQL Data Factory 2.0 — Quick Start

5-minute guide for immediate use.

---

## Option A: GUI (Recommended)

```bash
python scripts/ui_app.py
```

On bastion host:

```batch
bin\run_gui.bat
```

Follow the tab workflow:

1. **Connection** → Enter host/port/user/password/database → Test → Connect
2. **Scan** → Click "Scan Database" → Wait for cache
3. **Tasks** → Select tables, set row counts → Confirm
4. **Preview** → Review generated rows → looks OK? proceed
5. **Execute** → Click "Run Campaign"
6. **History** → View reports → Run Cleanup when done

---

## Option B: CLI Wizard

```bash
python scripts/wizard.py --env-file .env
```

On bastion host:

```batch
bin\run_wizard.bat
```

---

## Option C: Smoke Test (Quick Validation)

```bash
# Generate preview only (no insert)
python scripts/smoke_test.py --env-file .env

# Insert 10 test rows
python scripts/smoke_test.py --env-file .env --insert --rows 10
```

---

## .env Configuration

```ini
DB_HOST=your.host.com
DB_PORT=3306
DB_USER=your_user
DB_PASSWORD=your_password
DB_NAME=your_database
```

Copy from template:

```bash
cp .env.example .env
```

---

## 100k Row Pressure Test

```bash
python scripts/pressure_test_100k.py --env-file .env --table your_table --rows 100000
```

---

## Cleanup After Testing

```bash
# Dry-run first
python scripts/cleanup.py --env-file .env \
  --table your_table \
  --pk-column ID \
  --pk-start 100001 \
  --pk-end 200000 \
  --dry-run

# Execute delete
python scripts/cleanup.py --env-file .env \
  --table your_table \
  --pk-column ID \
  --pk-start 100001 \
  --pk-end 200000 \
  --execute
```

Or cleanup by campaign ID (uses saved reports):

```bash
python scripts/cleanup.py --env-file .env --campaign-id 20260402_143022_a1b2c3 --dry-run
```

---

## Key Files

| Path | Purpose |
|---|---|
| `scripts/ui_app.py` | Launch GUI |
| `scripts/wizard.py` | CLI wizard |
| `scripts/smoke_test.py` | Quick validation |
| `scripts/pressure_test_100k.py` | Large-scale test |
| `scripts/cleanup.py` | Delete test data |
| `bin\setup_offline.bat` | Deploy offline environment |
| `bin\run_gui.bat` | Launch GUI (bastion) |
| `data/output/` | Generated CSV chunks |
| `reports/` | Execution reports |
| `sql/cleanup/` | Cleanup SQL files |
| `metadata_cache/` | Cached DB scan results |
