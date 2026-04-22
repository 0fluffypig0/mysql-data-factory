# MySQL Data Factory 3.0.2

![version](https://img.shields.io/badge/version-3.0.2-blue)
![python](https://img.shields.io/badge/python-3.11-blue)
![license](https://img.shields.io/badge/license-MIT-green)
![platform](https://img.shields.io/badge/platform-Windows-lightgrey)

MySQL Data Factory is an offline-friendly MySQL test-data append tool for bastion-host environments. It ships as source code plus a prebuilt embeddable Python runtime archive, so the target machine only needs to unpack the project and run `bin\setup_offline.bat`.

The 3.0.2 line keeps the multi-table workflow and cleanup safety from 2.x, but removes the heavy PySide6/conda-pack path. The GUI is now `tkinter`, the offline runtime is a compact zip, and the batch insertion pipeline streams chunk files instead of holding the full campaign in memory.

---

## 3.0.2 Highlights

- `tkinter` GUI: no external GUI framework dependency, still keeps the 6-tab workflow
- Portable offline package: `env_export/mysql_factory_env.zip` is the official deployment artifact
- Low-memory batch insertion: chunk files are processed one by one during insert
- Multi-language UI: 简体中文 / English / 日本語
- Bastion-safe execution: short-lived insert connections, local runtime, no internet needed on target host
- Safer cleanup: campaign reports + generated cleanup SQL + dry-run/execute flow

---

## Verified on 2026-04-11

- Live integration test: 4 tables, 80,000 rows total, 0 failed batches
- Live pressure test: `t_email_send_log` appended 1,000,000 rows successfully
- Million-row throughput: about 18m55s total, about 893 rows/s on the tested environment
- Memory: Python-side peak memory stayed at about 68.6 MB during the 1,000,000-row traced run
- Offline runtime: `bin\setup_offline.bat`, `bin\test_connection.bat`, `tkinter` probe, and `bin\run_gui.bat` launch probe all passed
- Cleanup: both the 80,000-row and 1,000,000-row live test data sets were deleted back by exact PK range

---

## Recommended Delivery Model

Ship these two parts together:

1. Project source tree
2. `env_export/mysql_factory_env.zip`

That gives the bastion host a predictable install flow:

```batch
bin\setup_offline.bat
copy .env.example .env
bin\test_connection.bat
bin\run_gui.bat
```

`bin\setup_offline.bat` extracts the runtime into `runtime\mysql_factory_env\` inside the project directory, installs dependencies from the bundled `vendor/`, and verifies both `pymysql` and `tkinter`.

---

## Quick Start

Pick one of the two entry points:

### Local development (online machine)

> Use this if you have internet and just want to try the tool locally.

```bash
python scripts/ui_app.py
# or use the CLI wizard
python scripts/wizard.py --env-file .env
```

### Bastion host / offline machine (official path)

> Use this for the intended deployment: no network on target, bundled runtime.

```batch
bin\setup_offline.bat
copy .env.example .env
bin\test_connection.bat
bin\run_gui.bat
```

Prefer CLI over GUI on the bastion? Use `bin\run_wizard.bat`.

---

## Common Commands

```bash
# Connection test
python scripts/test_connection.py --env-file .env

# Preview-only smoke test
python scripts/smoke_test.py --env-file .env --table your_table --rows 5

# Real insert smoke test
python scripts/smoke_test.py --env-file .env --table your_table --rows 10 --insert

# Pressure test
python scripts/pressure_test_100k.py --env-file .env --table your_table --rows 100000

# Full V3 integration validation
python scripts/test_v3_full.py --env-file .env
```

---

## Repository Layout

```text
mysql-data-factory/
├── bin/                         # Windows entry points
├── config/                      # Local profiles and GUI preferences (runtime)
├── data/                        # Generated CSV chunks and previews (runtime)
├── env_export/
│   └── mysql_factory_env.zip    # Official offline runtime bundle
├── metadata_cache/              # Cached DB scans (runtime)
├── plans/                       # Saved campaign plans (runtime)
├── reports/                     # Execution reports (runtime)
├── runtime/                     # Extracted offline runtime after setup (runtime)
├── scripts/                     # Python entry points and build/test scripts
├── sql/cleanup/                 # Generated cleanup SQL (runtime)
├── src/                         # Core application code
├── .env.example                 # Connection template
├── requirements.txt             # Runtime pip dependencies
└── environment.yml              # Optional dev environment spec
```

---

## Documentation

| Document | Purpose | Audience |
|---|---|---|
| [QUICKSTART.md](QUICKSTART.md) | Fast 5-minute usage path | First-time users |
| [DEPLOYMENT.md](DEPLOYMENT.md) | Offline deployment and bastion-host usage | Ops / on-site engineers |
| [USER_GUIDE_3.0.md](USER_GUIDE_3.0.md) | GUI and CLI workflow reference | Daily users |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Module layout and data flow | Contributors |
| [RELEASE_NOTES_3.0.md](RELEASE_NOTES_3.0.md) | What changed in the 3.0.2 release | All users |
| [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md) | Release validation checklist | Maintainers |

---

## Runtime Dependencies

| Package | Version |
|---|---|
| Python | 3.11.x |
| PyMySQL | 1.1.2 |
| SQLAlchemy | current pinned by `requirements.txt` |
| python-dotenv | 1.2.2 |
| loguru | 0.7.3 |
| tabulate | current pinned by `requirements.txt` |
| tqdm | current pinned by `requirements.txt` |
| python-dateutil | current pinned by `requirements.txt` |

`tkinter` is provided by the bundled Python runtime and does not need a separate pip package.

---

## Versioning

- User-facing release name: `3.0.2`
- Semantic version / Git tag: `v3.0.2`

---

## License

MIT — see [LICENSE](LICENSE)






