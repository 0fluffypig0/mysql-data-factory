# MySQL Data Factory — Release Checklist

Use this checklist before each public release.

---

## Pre-Release Validation

### Core Functionality

- [ ] `python scripts/smoke_test.py` — passes without insert
- [ ] `python scripts/smoke_test.py --insert --rows 10` — 10 rows inserted OK
- [ ] `python scripts/pressure_test_100k.py --rows 100000` — 0 failed batches
- [ ] `python scripts/cleanup.py --dry-run` — correctly counts rows
- [ ] `python scripts/cleanup.py --execute` — correctly deletes rows
- [ ] `python scripts/wizard.py --help` — help text displays

### GUI

- [ ] GUI launches without error (`python scripts/ui_app.py`)
- [ ] Connection page: test + connect works
- [ ] Scan page: scan completes, tables listed
- [ ] Tasks page: table selection, row count, PK mode all configurable
- [ ] Preview page: generated data looks correct
- [ ] Execute page: campaign runs, progress updates in real time
- [ ] History page: reports and plans visible, cleanup works
- [ ] Language switcher: zh_CN / en / ja all switch correctly

### Cleanup Dialog

- [ ] Dry-run shows estimated rows per table
- [ ] Execute confirmation dialog shows ALL affected tables
- [ ] Execute actually deletes the rows

### Output Files

- [ ] Campaign directory uses new naming: `{ts}_JST__{short_id}__{db}/`
- [ ] Table directory naming: `{idx}__{table}__pk_{col}__rows_{n}/`
- [ ] `campaign_manifest.json` generated
- [ ] `campaign_summary.csv` generated
- [ ] `table_manifest.json` generated per table
- [ ] Cleanup SQL generated at `sql/cleanup/cleanup_{cid}.sql`
- [ ] Reports saved at `reports/report_{cid}_{table}.json`

---

## Repository State

### Files

- [ ] `README.md` is accurate and up to date
- [ ] `DEPLOYMENT.md` covers online build and offline deploy
- [ ] `ARCHITECTURE.md` reflects current code structure
- [ ] `USER_GUIDE_2.0.md` covers all main workflows
- [ ] `RELEASE_NOTES_2.0.md` lists all new features
- [ ] `QUICKSTART.md` provides 5-minute on-ramp
- [ ] `RELEASE_CHECKLIST.md` (this file) is complete
- [ ] `environment.yml` and `requirements.txt` are in sync
- [ ] `LICENSE` is present

### .gitignore

- [ ] `.env` excluded (credentials)
- [ ] `.env.local`, `.env.smoke`, `.env.remote_*` excluded
- [ ] `config/connection_profiles.json` excluded (credentials)
- [ ] `metadata_cache/` excluded (runtime data)
- [ ] `plans/`, `reports/`, `sql/cleanup/`, `data/output/` excluded (runtime data)
- [ ] `env_export/`, `delivery/`, `dist/` excluded (binaries)
- [ ] `.claude/` excluded (AI session data)
- [ ] `.gitkeep` files present in excluded runtime directories

### No Junk

- [ ] No temporary test files committed
- [ ] No real credentials in any committed file
- [ ] No leftover `TODAY_*.md` or `SPRINT_REPORT_*.md`
- [ ] `_audit_tmp/` not committed
- [ ] `task_templates/` excluded or empty

### Version

- [ ] Version string updated in `README.md` header
- [ ] `RELEASE_NOTES_2.0.md` has correct version and date
- [ ] Git tag created: `v2.0.0`

---

## Offline Deployment Validation (if new env build)

- [ ] `python scripts/build_offline_env.py` completes without error
- [ ] `env_export/mysql_factory_env.tar.gz` exists and is non-zero size
- [ ] `bin\setup_offline.bat` runs successfully on a clean machine
- [ ] `C:\tools\mysql_factory_env\python.exe --version` returns 3.11.x
- [ ] `import PySide6, pymysql, pandas` succeeds in offline env
- [ ] GUI and CLI work from the offline env

---

## Final Sign-Off

- [ ] All validation checks above completed
- [ ] 100k insertion test passed with 0 failures
- [ ] Cleanup of test data confirmed
- [ ] Documentation reviewed for accuracy
- [ ] Repository is clean (`git status` shows no untracked junk)
- [ ] Ready to tag `v2.0.0` and push to GitHub
