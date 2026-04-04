# MySQL Data Factory 2.0 — Release Notes

## Version 2.0.0

Release Date: 2026-04

---

## What's New in 2.0

### GUI (PySide6)

**New in 2.0** — a full-featured graphical interface replacing manual script workflows.

- **6-tab workflow**: Connection → Scan → Tasks → Preview → Execute → History
- **Multi-language support**: 简体中文 / English / 日本語 (switchable at runtime)
- **Persistent DB session**: One connection throughout the session — safe for bastion OTP environments
- **Real-time execution progress**: Phase (sample/generate/insert), rows/s, ETA, chunk and batch counters
- **Task template save/load**: Save a multi-table configuration and reload it in future sessions
- **History browser**: View all past campaigns, reports, and cleanup SQL in one place
- **High-safety cleanup confirmation dialog**: Shows all affected tables with PK ranges and estimated row counts before deletion

### Multi-Table Campaigns

**New in 2.0** — run multiple tables in a single campaign.

- Each table has its own configuration (row count, PK mode, sample method, batch size)
- All tables share one campaign ID for consistent cleanup
- Campaign-level manifest (`campaign_manifest.json`) and summary CSV generated automatically

### Evidence-Quality Output Naming

**New in 2.0** — human-readable, timestamp-based output directory names.

```
data/output/
└── 20260402_143022_JST__a1b2c3__ji_test/       ← campaign dir
    ├── campaign_manifest.json
    ├── campaign_summary.csv
    └── 01__t_travel__pk_TRAVEL_ID__rows_5000/  ← table dir
        ├── table_manifest.json
        └── chunk_*.csv
```

All chunk files include the row range in their filename for traceability.

### Enhanced Cleanup

**New in 2.0**:

- Cleanup targets all tables in a campaign (not just the most recent)
- GUI confirmation dialog lists every table with PK range and COUNT estimate
- CLI cleanup supports: campaign ID, PK range, marker column, or combination
- Cleanup reports saved alongside execution reports

### PK Range Modes

**New in 2.0** — explicit control over PK sequencing:

| Mode | Description |
|---|---|
| `auto_increment_from_max` | Default: starts from `MAX(pk) + 1` |
| `fixed_start` | User-specified start; does not check MAX(pk) |
| `explicit_range` | User-specified start and end |

### Complex PK Pattern Support

**Preserved and enhanced** from 1.x:

- Zero-padded strings: `"00000001"` → `"00000002"`
- Prefix + number: `"KC0007"` → `"KC0008"`, `"AXC000000997"` → `"AXC000000998"`
- Composite PKs (multiple PK columns each independently incremented)

### Metadata Cache

**Improved in 2.0**:

- Scan once per database, reuse across sessions
- Cache stored as JSON in `metadata_cache/`
- Compatible with scan-heavy databases (75+ tables scanned and cached automatically)

### CLI Wizard

**New in 2.0** — interactive terminal wizard for environments without GUI.

```batch
bin\run_wizard.bat
```

Guides through connection → table selection → row count → mode → execution.

---

## Verified Capabilities (2.0.0)

The following have been validated against a live MySQL 8.4 database:

| Scenario | Result |
|---|---|
| Connect and scan 75 tables | ✅ |
| Scan cache (load vs. re-scan) | ✅ |
| Preview generation (5 rows) | ✅ |
| Insert 20 rows (smoke test) | ✅ |
| Insert 100,000 rows (pressure test) | ✅ (0 failures) |
| Generate throughput | ~55,000 rows/s |
| Insert throughput (remote) | ~2,000 rows/s |
| CLI cleanup dry-run | ✅ |
| CLI cleanup execute | ✅ |
| Output manifests (campaign + table) | ✅ |
| Cleanup SQL generation | ✅ |

---

## Known Limitations

### Bastion Host Throughput

Insert throughput is network-bound. On a high-latency connection (~50ms RTT):

- Expected insert rate: 500–2,000 rows/s
- 100,000 rows: ~1–3 minutes
- 1,000,000 rows: ~10–30 minutes

**Recommendation**: Use `batch_size=1000` or higher and `chunk_size=10000` for large campaigns.

### GUI Not Validated on Bastion

The GUI has not been end-to-end tested on a bastion host (requires display forwarding). CLI (`bin\run_wizard.bat`) is the recommended bastion entry point for headless environments.

### No Parallel Table Insertion

Tables within a campaign are inserted sequentially, not in parallel. Multi-table campaigns on large databases may take proportionally longer.

### scan_database Re-scan in Standalone Scripts

`scripts/smoke_test.py` always re-scans the database. The `pressure_test_100k.py` now uses the cache (fixed in 2.0.0). The GUI always uses the cached result.

---

## Upgrade from 1.x

V1.x CLI scripts remain fully functional:

```batch
bin\expand_rows.bat
bin\insert_csv.bat
bin\export_sample.bat
bin\scan_table_info.bat
bin\test_connection.bat
```

2.0 adds the GUI and wizard as primary interfaces. V1.x scripts are now considered legacy.

---

## Dependencies

| Package | Version | Purpose |
|---|---|---|
| Python | 3.11 | Runtime |
| PyMySQL | 1.1.2 | MySQL driver |
| pandas | 2.3.3 | Data manipulation |
| PySide6 | ≥6.6 | GUI framework |
| loguru | 0.7.3 | Structured logging |
| python-dotenv | 1.2.2 | .env loading |
| numpy | 2.2.6 | Numerical operations |
