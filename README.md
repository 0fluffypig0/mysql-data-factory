# MySQL Data Factory 2.0

A local, offline-capable MySQL test data generation and insertion tool — with GUI, multi-table campaign orchestration, complex PK pattern support, and full cleanup lifecycle.

Designed for **bastion host environments**: build your test data package on an online machine, then insert it on an air-gapped database host with no internet access.

---

## Features

- **GUI** (PySide6): 6-tab workflow from connection to cleanup, with real-time progress
- **Multi-language**: 简体中文 / English / 日本語
- **Multi-table campaigns**: Configure and insert N tables in one run
- **Complex PK patterns**: integers, zero-padded strings (`"00000001"`), prefix+number (`"KC0007"`)
- **PK range modes**: `auto_increment_from_max` / `fixed_start` / `explicit_range`
- **Metadata cache**: Scan once, reuse across sessions
- **Sample selection**: by first row, PK lookup, or WHERE clause
- **Batch insertion**: short-lived connections per batch — bastion-safe
- **Evidence output**: human-readable directory names, `campaign_manifest.json`, `table_manifest.json`
- **Cleanup lifecycle**: generated SQL, dry-run COUNT, execute with high-safety confirmation dialog
- **Offline deployment**: conda-pack to bastion host, zero internet required at runtime
- **CLI wizard and legacy V1.x scripts**: all still functional

---

## Quick Start

### GUI

```bash
python scripts/ui_app.py
```

On bastion host:

```batch
bin\run_gui.bat
```

Workflow: **Connection** → **Scan** → **Tasks** → **Preview** → **Execute** → **History**

### CLI Wizard

```bash
python scripts/wizard.py --env-file .env
```

### Smoke Test

```bash
# Preview only
python scripts/smoke_test.py --env-file .env

# Preview + insert 10 rows
python scripts/smoke_test.py --env-file .env --insert --rows 10
```

---

## Configuration

Copy `.env.example` to `.env` and fill in your credentials:

```ini
DB_HOST=your.db.host
DB_PORT=3306
DB_USER=your_user
DB_PASSWORD=your_password
DB_NAME=your_database
```

---

## Directory Structure

```
mysql-data-factory/
├── bin/                      # Windows batch entry points
│   ├── setup_offline.bat     # Deploy offline Python environment
│   ├── run_gui.bat           # Launch GUI
│   ├── run_wizard.bat        # Launch CLI wizard
│   ├── run_cleanup.bat       # Run cleanup
│   └── test_connection.bat   # Test DB connectivity
│
├── scripts/                  # Python entry points
│   ├── ui_app.py             # GUI application
│   ├── wizard.py             # CLI wizard
│   ├── cleanup.py            # Cleanup CLI
│   ├── smoke_test.py         # Smoke test
│   ├── pressure_test_100k.py # 100k row pressure test
│   └── build_offline_env.py  # Build offline package
│
├── src/                      # Core library
│   ├── config/               # .env, connection profiles, app paths
│   ├── db/                   # Database connection, queries
│   ├── metadata/             # DB scan, models, caching
│   ├── sample/               # Sample record selection
│   ├── strategy/             # PK planning, field strategies
│   ├── plan/                 # TaskItem, CampaignPlan models
│   ├── generate/             # Row building, chunk generation
│   ├── execute/              # Batch insertion, cleanup execution
│   ├── report/               # History, report management
│   ├── workflow/             # Campaign orchestration
│   ├── ui/                   # PySide6 GUI pages
│   └── utils/                # Timezone, common helpers
│
├── metadata_cache/           # Cached DB scan results (runtime, gitignored)
├── plans/                    # Campaign plan files (runtime, gitignored)
├── reports/                  # Execution reports (runtime, gitignored)
├── data/output/              # Generated chunk CSVs (runtime, gitignored)
├── sql/cleanup/              # Cleanup SQL files (runtime, gitignored)
├── config/                   # Connection profiles (runtime, gitignored)
│
├── environment.yml           # Conda environment spec
├── requirements.txt          # Pip dependencies
├── .env.example              # Configuration template
└── LICENSE                   # MIT
```

---

## Core Concepts

### Campaign

A batch of table tasks executed together. Gets a unique `campaign_id` used for tracking, output directories, cleanup SQL, and reports.

### TaskItem

Configuration for one table: row count, batch size, sample method, PK range mode, execution mode, marker column.

### PK Range Planning

| Mode | Description |
|---|---|
| `auto_increment_from_max` | Queries `MAX(pk)+1` as the start (safe default) |
| `fixed_start` | User-specified start value |
| `explicit_range` | User-specified start and end |

Supports integer PKs, zero-padded strings, and prefix+number patterns automatically.

### Cleanup

Every campaign generates cleanup SQL targeting the exact PK ranges inserted. Supports dry-run (COUNT) and execute modes, with a high-safety per-table confirmation dialog in the GUI.

---

## Offline Deployment

1. **Online machine**: Build the package
   ```bash
   python scripts/build_offline_env.py
   # → env_export/mysql_factory_env.tar.gz
   ```

2. **Transfer**: Copy repo + `env_export/` to bastion host

3. **Bastion host**: Deploy
   ```batch
   bin\setup_offline.bat
   ```

4. **Run**:
   ```batch
   bin\run_gui.bat
   bin\run_wizard.bat
   ```

For full details: [DEPLOYMENT.md](DEPLOYMENT.md)

---

## Documentation

| Document | Purpose |
|---|---|
| [QUICKSTART.md](QUICKSTART.md) | 5-minute on-ramp |
| [USER_GUIDE_2.0.md](USER_GUIDE_2.0.md) | Complete GUI and CLI reference |
| [DEPLOYMENT.md](DEPLOYMENT.md) | Offline deployment and bastion host setup |
| [ARCHITECTURE.md](ARCHITECTURE.md) | System design and module reference |
| [RELEASE_NOTES_2.0.md](RELEASE_NOTES_2.0.md) | What's new in 2.0, verified capabilities |
| [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md) | Pre-release validation checklist |

---

## Dependencies

| Package | Version |
|---|---|
| Python | 3.11+ |
| PyMySQL | 1.1.2 |
| pandas | 2.3.3 |
| PySide6 | ≥6.6 |
| loguru | 0.7.3 |
| python-dotenv | 1.2.2 |

See `requirements.txt` or `environment.yml` for the full list.

---

## License

MIT — see [LICENSE](LICENSE)
