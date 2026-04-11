# MySQL Data Factory 3.0.1 — Deployment Guide

This guide describes the release model used by 3.0.1:

- keep the project source code
- keep `env_export\mysql_factory_env.zip`
- on the bastion host, unpack once and run `bin\setup_offline.bat`

No Conda and no internet access are required on the target machine.

---

## Recommended Package Layout

```text
mysql-data-factory/
├── bin/
├── scripts/
├── src/
├── env_export/
│   └── mysql_factory_env.zip
└── .env.example
```

This is the artifact you publish or transfer.

---

## Maintainer Workflow

### When You Need to Rebuild the Runtime

Rebuild `env_export\mysql_factory_env.zip` only when one of these changes:

- Python version
- `requirements.txt`
- offline packaging logic in `scripts/build_offline_env.py`
- bundled GUI runtime requirements (`tkinter` / Tcl / Tk layout)

Command:

```bash
python scripts/build_offline_env.py
```

Output:

```text
env_export/
└── mysql_factory_env.zip
```

### When You Do Not Need to Rebuild the Runtime

If you only changed application code or docs, you can usually publish source updates without regenerating the archive. For the 3.0.1 release, the archive is already prepared and intended to travel together with the source tree.

---

## Bastion-Host Installation

### Step 1: Unpack the Project

Copy or unzip the project directory to the bastion host.

### Step 2: Install the Bundled Runtime

```batch
bin\setup_offline.bat
```

What it does:

1. extracts `env_export\mysql_factory_env.zip`
2. installs pip dependencies from the bundled `vendor/`
3. verifies `python.exe`
4. verifies `pymysql`
5. verifies `tkinter` and Tcl/Tk runtime wiring

Resulting layout:

```text
runtime/
└── mysql_factory_env/
    ├── python/
    └── vendor/
```

### Step 3: Configure the Database

```batch
copy .env.example .env
```

Edit `.env` with your target database credentials.

### Step 4: Confirm Connectivity

```batch
bin\test_connection.bat
```

### Step 5: Run the Tool

GUI:

```batch
bin\run_gui.bat
```

CLI wizard:

```batch
bin\run_wizard.bat
```

---

## Project-Relative Runtime Model

3.0.1 installs the runtime under the project directory instead of a global path like `C:\tools\...`.

Benefits:

- easier to copy as one bundle
- no machine-wide installation requirement
- safer for restricted bastion hosts
- simpler cleanup and replacement

The batch files still contain backward-compatible fallback logic for older `C:\tools\mysql_factory_env\python.exe` installs, but the recommended path is the project-local `runtime\mysql_factory_env\python\python.exe`.

---

## Validation Checklist on the Target Machine

Run these after installation:

```batch
runtime\mysql_factory_env\python\python.exe --version
bin\test_connection.bat
bin\run_gui.bat
```

Optional quick pipeline validation:

```bash
python scripts/smoke_test.py --env-file .env --table your_table --rows 5
```

Optional real insert validation:

```bash
python scripts/smoke_test.py --env-file .env --table your_table --rows 10 --insert
```

---

## Troubleshooting

### `Offline environment package not found`

`bin\setup_offline.bat` expects:

```text
env_export\mysql_factory_env.zip
```

If it is missing, rebuild it on the maintainer machine:

```bash
python scripts/build_offline_env.py
```

### `tkinter import check failed`

This usually means the runtime archive is incomplete or the Tcl/Tk files were not bundled correctly. Rebuild the runtime with the current `scripts/build_offline_env.py` and replace the old zip.

### `Offline Python environment not found`

Run:

```batch
bin\setup_offline.bat
```

This should create:

```text
runtime\mysql_factory_env\python\python.exe
```

### Database Connection Fails

Check:

- `.env` contents
- network reachability from the bastion host
- firewall / VPN / whitelist rules
- target MySQL account permissions

---

## Release Recommendation

For 3.0.1, treat the following as the official release payload:

1. project source tree
2. `env_export\mysql_factory_env.zip`

That keeps deployment simple for downstream users: unpack, configure `.env`, run setup, then launch.


