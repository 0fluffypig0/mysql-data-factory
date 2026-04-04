# MySQL Data Factory 2.0 — Deployment Guide

This guide covers two scenarios:

1. **Online machine**: Building the offline package from source
2. **Bastion host / offline machine**: Deploying and using the tool without internet

---

## Part 1: Online Machine — Build the Offline Package

### Prerequisites

- Conda (Anaconda or Miniconda) installed
- Python 3.11+
- Internet access (for downloading packages)

### Step 1: Create the Conda Environment

```bash
conda env create -f environment.yml
conda activate mysql_factory_env
```

### Step 2: Build the Offline Package

```bash
python scripts/build_offline_env.py
```

This runs `conda-pack` to produce:

```
env_export/
└── mysql_factory_env.tar.gz   (~500 MB compressed)
```

### Step 3: Transfer to the Bastion Host

Copy the entire repository **plus** the generated archive:

```
mysql-data-factory/        ← entire repo directory
env_export/
└── mysql_factory_env.tar.gz
```

You may zip the whole project folder for transfer:

```bash
# Example
zip -r mysql-data-factory-v2.0.zip mysql-data-factory/ env_export/
```

---

## Part 2: Bastion Host — Deploy the Offline Environment

### Prerequisites

- Windows (x64) — scripts are `.bat` based
- No internet required after deployment
- ~1.5 GB free disk space for the extracted Python environment

### Step 1: Deploy the Offline Environment

Run the setup script from the project directory:

```batch
cd mysql-data-factory
bin\setup_offline.bat
```

This will:

1. Extract `env_export\mysql_factory_env.tar.gz` to `C:\tools\mysql_factory_env\`
2. Run `conda-unpack.exe` to make the environment relocatable
3. Verify `python.exe` is working

Expected output:

```
[INFO] Extracting environment...
[INFO] Running conda-unpack...
[OK] Python 3.11.x

Next steps:
  1. Copy .env.example to .env and fill in your DB credentials
  2. Run: bin\test_connection.bat
  3. Run: bin\run_gui.bat
```

### Step 2: Configure Database Connection

```batch
copy .env.example .env
notepad .env
```

Fill in:

```ini
DB_HOST=your.db.host
DB_PORT=3306
DB_USER=your_username
DB_PASSWORD=your_password
DB_NAME=your_database
```

### Step 3: Test the Connection

```batch
bin\test_connection.bat
```

Expected:

```
[OK] Connected to your_database (N tables found)
```

### Step 4: Launch the GUI

```batch
bin\run_gui.bat
```

Or use the CLI wizard:

```batch
bin\run_wizard.bat
```

---

## Offline Environment Validation

After deployment, run a quick validation to confirm all components work:

```batch
C:\tools\mysql_factory_env\python.exe --version
```

```batch
C:\tools\mysql_factory_env\python.exe -c "import PySide6, pymysql, pandas; print('All OK')"
```

```batch
bin\test_connection.bat
```

```batch
C:\tools\mysql_factory_env\python.exe scripts\smoke_test.py
```

---

## Troubleshooting

### `[ERROR] Offline Python environment not found`

The `.bat` files look for Python at `C:\tools\mysql_factory_env\python.exe`.
Run `bin\setup_offline.bat` first, or update the `ENV_PYTHON` variable in the batch files if you installed to a different location.

### `conda-unpack not found`

The conda-pack archive may be incomplete. Rebuild it on the online machine:

```bash
pip install conda-pack
python scripts/build_offline_env.py
```

### Connection failures

- Verify host/port/credentials in `.env`
- Check VPN or firewall rules for bastion host
- Test with `telnet your.db.host 3306`

### GUI doesn't launch

Verify PySide6 is installed:

```batch
C:\tools\mysql_factory_env\python.exe -c "import PySide6; print(PySide6.__version__)"
```

If missing, rebuild the offline package with PySide6 included (check `environment.yml`).

---

## Directory Layout After Deployment

```
C:\tools\mysql_factory_env\   ← Python environment (offline)

mysql-data-factory\           ← Project root
├── bin\                      ← Batch entry points
├── scripts\                  ← Python entry points
├── src\                      ← Core library
├── data\output\              ← Generated CSV chunks (runtime)
├── metadata_cache\           ← Cached DB scan results (runtime)
├── plans\                    ← Campaign plans (runtime)
├── reports\                  ← Execution reports (runtime)
├── sql\cleanup\              ← Cleanup SQL files (runtime)
├── .env                      ← Your local credentials (never commit)
├── environment.yml           ← Conda environment spec
└── requirements.txt          ← Pip dependencies
```

---

## Re-deployment / Updates

To update the tool without rebuilding the Python environment:

1. Copy only the project files (not `env_export/`)
2. The Python environment at `C:\tools\mysql_factory_env\` is reused

To update the Python environment:

1. Rebuild the package on the online machine
2. Delete `C:\tools\mysql_factory_env\` on the bastion host
3. Run `bin\setup_offline.bat` again
