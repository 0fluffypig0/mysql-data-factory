# MySQL Data Factory 3.0.2 — Release Notes

## Version 3.0.2

Release Date: 2026-04-22

---

## What Changed in 3.0.2

### New: PostgreSQL + Oracle dialect support

3.0.2 extends the SQLAlchemy-based data engine from MySQL-only to four dialects:

- **MySQL** 5.7 / 8.0 / 8.4, MariaDB 10.x / 11.x, Aurora MySQL, Percona
- **PostgreSQL** 12–16, Aurora PostgreSQL, Cloud SQL PG, TimescaleDB
- **Oracle** 12c / 19c / 21c / 23ai, Autonomous DB, Exadata (thin mode, no Instant Client)
- **SQLite** single-file and `:memory:`

URL construction uses `urllib.parse.quote_plus` for every user/password, so passwords
with `@`, `/`, `:` and similar special characters work out of the box. Oracle uses
`oracle+oracledb://user:pw@host:port/?service_name=XYZ` (Easy Connect compatible) and
runs in python-oracledb's **thin** mode — no Oracle Instant Client install is required
on bastion hosts.

New dependencies in `requirements.txt`:

- `psycopg2-binary` (bundled libpq — no system deps)
- `oracledb` (thin mode)

### New: Connection page now self-documents supported engines

The dialect dropdown no longer shows raw internal IDs. Each option is now a
human-readable label paired with a live info panel that shows:

- the Python driver in use
- the list of real engines each dialect covers (so coworkers can tell which option
  matches the server they are targeting)
- fastpath / thin-mode notes

Dialect-specific behavior baked in:

- port auto-fills to the default for the selected dialect (3306 / 5432 / 1521),
  but only when the user has not customized it
- charset is disabled for non-MySQL dialects
- SQLite hides host / port / user / password and shows a file Browse button
- Oracle shows a hint explaining `service_name` vs SID

All 7 new UI strings are wired through `src/ui/i18n.py` (zh_CN / en / ja).

### Fix: GUI exe no longer crashes on tkinter DLL load

Previous behavior:

- Building with PyInstaller on top of Miniforge / conda-forge Python produced an
  exe that crashed immediately on launch with
  `ImportError: DLL load failed while importing _tkinter: tcl86t.dll`
- Root cause: PyInstaller's stock tkinter hook assumes a standard CPython layout
  (`DLLs\` + `tcl\`). Miniforge instead ships tcl/tk under `Library\bin\` and
  `Library\lib\`, which the hook does not scan.

Current behavior:

- `mysql_factory.spec` now declares `tcl86t.dll`, `tk86t.dll`, `tcl8.6/` and
  `tk8.6/` as explicit `binaries` and `datas` entries, pointing at the Miniforge
  paths
- The built exe initializes tkinter cleanly on a fresh Windows machine with no
  Python installed

### Fix: All dialect drivers now bundled into the exe

`mysql_factory.spec` declares as `hiddenimports`:

- `psycopg2`, `oracledb`, `oracledb.thin_impl`
- `sqlalchemy.dialects.mysql.pymysql`
- `sqlalchemy.dialects.postgresql.psycopg2`
- `sqlalchemy.dialects.oracle.oracledb`
- `sqlalchemy.dialects.sqlite.pysqlite`

SQLAlchemy resolves dialect modules via entry points at runtime, which PyInstaller
can miss — pinning them explicitly guarantees all four dialects work in the packaged
exe without a live Python environment.

---

## Carry-Forward Capabilities from 3.0.1

Unchanged from 3.0.1:

- tkinter-based GUI, 6-tab workflow
- streamed chunk-file batch insertion for low memory usage on million-row campaigns
- append-only cleanup safety
- Asia/Tokyo timestamps throughout
- `exportselection=False` stability fix on the Tasks page

---

## Release Delivery Recommendation

The preferred artifact for downstream users is:

1. source code (this repo at tag `v3.0.2`)
2. `mysql_factory_3.0.2_win64.zip` — a self-contained `--onedir` PyInstaller bundle
   that runs on any 64-bit Windows machine with no Python install

Target-machine workflow:

- unzip
- copy `.env.example` to `.env` and fill in credentials (any of the 4 dialects)
- run `mysql_factory.exe`

---

## Compatibility Notes

- Git tag for this release is `v3.0.2`
- user-facing release name is `3.0.2`
- fully backward-compatible with 3.0.1 `.env` files and task configs (new dialect
  fields default to MySQL)

---

## Version 3.0.1

Release Date: 2026-04-11

---

## What Changed in 3.0.1

### Bug Fix: Task Config Panel No Longer Disappears While Editing

Fixed a GUI interaction issue on the Tasks page.

Previous behavior:

- after selecting a task in the left task list
- when changing a combobox on the right-side config panel, such as sample method, PK mode, or execution mode
- the left-side task selection could be cleared by focus transfer
- the right-side config area would then disappear until the user clicked the table name again

Current behavior:

- the selected task remains selected while focus moves into the right-side configuration widgets
- the right-side configuration panel stays visible during combobox edits
- task editing now feels stable and continuous

Implementation note:

- `src/ui/page_tasks.py` now creates the task list with `exportselection=False`, which preserves the Listbox selection while the user interacts with widgets on the right

---

## Carry-Forward Capabilities from 3.0.0

The following remain unchanged from the initial 3.0 release:

- tkinter-based GUI
- embeddable Python offline runtime bundle
- `env_export/mysql_factory_env.zip` as the portable deployment artifact
- streamed chunk-file batch insertion for low memory usage
- bastion-host-friendly local runtime and append workflow

---

## Release Delivery Recommendation

For 3.0.1, the preferred way to hand the tool to downstream users is still:

1. source code
2. `env_export/mysql_factory_env.zip`

That keeps the target-machine workflow simple:

- unpack once
- configure `.env`
- run setup
- start using the tool

---

## Compatibility Notes

- Git tag for this release is `v3.0.1`
- user-facing release name is `3.0.1`
- the release is a small bugfix update on top of `v3.0.0`
