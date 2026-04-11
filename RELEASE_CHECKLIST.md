# MySQL Data Factory 3.0.1 — Release Checklist

Use this checklist before publishing a new 3.x release.

---

## Core Validation

- [ ] `python scripts/test_connection.py --env-file .env` succeeds
- [ ] `python scripts/smoke_test.py --env-file .env --table <table> --rows 5` succeeds
- [ ] `python scripts/smoke_test.py --env-file .env --table <table> --rows 10 --insert` succeeds
- [ ] `python scripts/pressure_test_100k.py --env-file .env --table <table> --rows 100000` completes without failed batches
- [ ] `python scripts/cleanup.py --dry-run` works on saved report data
- [ ] `python scripts/cleanup.py --execute` deletes the intended rows only
- [ ] `python scripts/wizard.py --help` prints normally
- [ ] `python scripts/test_v3_full.py --env-file .env` passes if a full live validation is required for the release

---

## GUI Validation

- [ ] `python scripts/ui_app.py` launches locally
- [ ] `bin\run_gui.bat` launches from the offline runtime
- [ ] Connection page works
- [ ] Scan page works
- [ ] Tasks page works
- [ ] Preview page works
- [ ] Execute page works
- [ ] History page works
- [ ] zh_CN / en / ja language switching works

---

## Offline Bundle Validation

- [ ] `python scripts/build_offline_env.py` completes without error
- [ ] `env_export/mysql_factory_env.zip` exists and is non-zero size
- [ ] `bin\setup_offline.bat` succeeds on a clean unpacked project
- [ ] `runtime\mysql_factory_env\python\python.exe --version` works
- [ ] `import pymysql` succeeds in the offline runtime
- [ ] `import tkinter` succeeds in the offline runtime
- [ ] `bin\test_connection.bat` succeeds from the offline runtime

---

## Repository Hygiene

- [ ] `README.md` matches the current release behavior
- [ ] `DEPLOYMENT.md` matches the current packaging flow
- [ ] `ARCHITECTURE.md` reflects the tkinter + embeddable runtime design
- [ ] `USER_GUIDE_3.0.md` reflects the current GUI/CLI workflow
- [ ] `RELEASE_NOTES_3.0.md` matches the tested release state
- [ ] `.gitignore` excludes runtime and generated data correctly
- [ ] no real credentials are tracked
- [ ] no `runtime/`, `data/`, `reports/`, or other generated junk are tracked accidentally

---

## Versioning

- [ ] user-facing release version is `3.0.1`
- [ ] package semantic version is `3.0.1`
- [ ] Git tag prepared: `v3.0.1`

---

## Final Sign-Off

- [ ] release artifact reviewed
- [ ] source tree reviewed
- [ ] offline install path verified
- [ ] cleanup safety verified
- [ ] ready to push `main`
- [ ] ready to push tag `v3.0.1`





