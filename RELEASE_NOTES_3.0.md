# MySQL Data Factory 3.00 — Release Notes

## Version 3.0.0

Release Date: 2026-04-11

---

## What Changed in 3.00

### 1. GUI Stack Slimmed Down

The GUI moved from PySide6 to `tkinter`.

Why this matters:

- removes the largest dependency from the distribution
- keeps the desktop workflow available on restricted Windows hosts
- makes offline packaging much smaller and easier to carry around

The six-tab workflow remains intact:

- Connection
- Scan
- Tasks
- Preview
- Execute
- History

### 2. Offline Deployment Rebuilt Around Embeddable Python

The old conda-pack path was replaced by a compact runtime bundle built from:

- Python embeddable package
- bundled wheel files in `vendor/`
- copied `tkinter` / Tcl / Tk runtime assets

Official release artifact:

```text
env_export/mysql_factory_env.zip
```

Target-machine flow:

```batch
bin\setup_offline.bat
bin\test_connection.bat
bin\run_gui.bat
```

### 3. Million-Row Memory Path Fixed

`src/execute/batch_runner.py` no longer accumulates every generated row into one in-memory list before insertion. Instead, it streams chunk files one by one and splits each chunk into insert batches on demand.

Impact:

- much lower peak memory usage
- better fit for weak bastion hosts
- safer large-table append jobs

### 4. Dependency Footprint Reduced

Removed heavy runtime dependencies from the main path, including:

- PySide6
- pandas
- numpy
- pyarrow
- openpyxl
- IPython

Retained core runtime dependencies:

- PyMySQL
- SQLAlchemy
- python-dotenv
- loguru
- tabulate
- tqdm
- python-dateutil

---

## Verified Results for 3.00

The following were revalidated on 2026-04-11 against a live MySQL environment.

| Scenario | Result |
|---|---|
| 4-table live integration test | 80,000 rows inserted, 0 failed batches |
| Million-row live append test | 1,000,000 rows inserted into `t_email_send_log` |
| Million-row elapsed time | about 18m55.4s |
| Million-row insert throughput | about 893 rows/s |
| Python peak memory during traced 1M run | about 68.6 MB |
| Offline connection test | passed |
| Offline `tkinter` probe | passed |
| Offline GUI launch probe | passed |
| Cleanup of inserted test rows | passed |

---

## Release Delivery Recommendation

For 3.00, the preferred way to hand the tool to downstream users is:

1. source code
2. `env_export/mysql_factory_env.zip`

That allows the bastion host to stay simple:

- unpack once
- configure `.env`
- run setup
- start using the tool

---

## Compatibility Notes

- Git tag for this release is `v3.0.0`
- user-facing release name is `3.00`
- legacy batch entry points remain available for older script-based workflows
- batch files still have fallback support for older `C:\tools\mysql_factory_env\python.exe` installs, but project-local `runtime\mysql_factory_env\...` is now the primary path

---

## Operational Recommendation

3.00 is suitable for:

- offline bastion deployment
- append-only test data generation
- million-row scale campaigns where low memory matters
- teams that want one portable folder instead of machine-wide environment setup
