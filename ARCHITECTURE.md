# MySQL Data Factory 3.00 — Architecture

## Overview

MySQL Data Factory 3.00 is built for one practical goal: append large volumes of test data into real MySQL schemas from restricted environments without dragging along a heavy runtime.

The release is centered on three architectural shifts:

- `tkinter` replaces PySide6 for the desktop workflow
- an embeddable Python zip replaces the old conda-pack deployment path
- batch insertion streams chunk files instead of preloading the whole campaign into memory

```text
┌─────────────────────────────────────────────────────────────────┐
│                        User Interfaces                          │
│                                                                 │
│   tkinter GUI             CLI Wizard          Scripted Tools     │
│   scripts/ui_app.py       scripts/wizard.py   scripts/*.py      │
└────────────────┬────────────────┬──────────────────────────────┘
                 │                │
                 ▼                ▼
┌─────────────────────────────────────────────────────────────────┐
│                       Workflow Layer                            │
│                                                                 │
│         src/workflow/campaign_runner.py                         │
│     sample -> generate chunks -> insert -> report -> cleanup   │
└──────┬────────────┬──────────────┬──────────────────┬──────────┘
       │            │              │                  │
       ▼            ▼              ▼                  ▼
┌──────────┐ ┌──────────┐ ┌────────────┐ ┌──────────────────────┐
│  Sample  │ │ Generate │ │  Execute   │ │      Report          │
│ selector │ │  chunks  │ │  batches   │ │ history + cleanup    │
└──────────┘ └──────────┘ └────────────┘ └──────────────────────┘
       │            │              │
       ▼            ▼              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Infrastructure Layer                        │
│                                                                 │
│   src/db/connection.py    src/metadata/scanner.py              │
│   src/config/app_config.py  src/strategy/pk_planner.py         │
└─────────────────────────────────────────────────────────────────┘
```

---

## Deployment Model

The runtime is delivered as:

- source code
- `env_export/mysql_factory_env.zip`

On the target machine, `bin\setup_offline.bat` expands that archive into `runtime\mysql_factory_env\` and installs dependencies from the bundled wheels. This keeps the deployment project-relative and easy to move around as one folder.

---

## Core Workflow

### 1. Metadata Scan

`src/metadata/scanner.py` inspects tables, columns, PKs, unique keys, JSON columns, marker candidates, and current row counts. Results are cached under `metadata_cache/`.

### 2. Sample Selection

`src/sample/selector.py` pulls one real row from the target table and normalizes it into a template row.

### 3. PK Planning

`src/strategy/pk_planner.py` computes the insertion range based on:

- `auto_increment_from_max`
- `fixed_start`
- `explicit_range`

The planner supports integer, zero-padded string, and prefix-plus-number PK shapes.

### 4. Chunk Generation

`src/generate/row_builder.py` writes generated rows to CSV chunk files on disk. This keeps generation deterministic and produces evidence artifacts that can be inspected later.

### 5. Streaming Batch Insert

`src/execute/batch_runner.py` reads one chunk file at a time and breaks it into insert batches. The important 3.00 behavior is that it no longer builds an in-memory list of every generated row before insert. That change is what keeps million-row campaigns within low double-digit MB memory usage on the Python side.

### 6. Reporting and Cleanup

`src/workflow/campaign_runner.py` and `src/report/history.py` write:

- `campaign_manifest.json`
- `campaign_summary.csv`
- per-table `table_manifest.json`
- per-table JSON reports
- generated cleanup SQL under `sql/cleanup/`

---

## GUI Architecture

The GUI lives under `src/ui/` and is now a pure `tkinter` application.

Key conversions in 3.00:

- `MainWindow` wraps `tk.Tk()` instead of `QMainWindow`
- background work uses `threading.Thread` with `widget.after(...)` callbacks instead of Qt threads/signals
- `SessionManager` uses plain Python callbacks instead of `QObject`
- table displays use `ttk.Treeview`
- modal dialogs use `tk.Toplevel`, `grab_set()`, and `wait_window()`

The six-tab flow remains the same:

1. Connection
2. Scan
3. Tasks
4. Preview
5. Execute
6. History

---

## Connection Strategy

The tool prefers explicit control over connection lifetime.

- GUI session tasks can reuse a persistent connection through `SessionManager`
- batch inserts can use short-lived connections per batch, which is safer on unstable bastion links
- cleanup and scan operations are isolated and explicit

This balance keeps the workflow usable on restrictive environments while still supporting long-running append jobs.

---

## Important Runtime Directories

These directories are runtime data, not source:

- `config/`
- `data/`
- `metadata_cache/`
- `plans/`
- `reports/`
- `runtime/`
- `sql/cleanup/`
- `task_templates/`

They are intentionally excluded from normal source-control history, except for the official release archive `env_export/mysql_factory_env.zip`.
