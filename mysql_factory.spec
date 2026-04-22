# PyInstaller spec for MySQL Data Factory 3.0.2 (GUI, --onedir).
#
# Build:
#   pyinstaller --noconfirm mysql_factory.spec
#
# Output:
#   dist/mysql_factory/mysql_factory.exe  (+ _internal/ sibling dir with Python + deps)
#
# After build, copy these alongside mysql_factory.exe for the user:
#   .env.example  (so users copy it to .env and fill in creds)
# (scripts/build_exe.py does this automatically.)

block_cipher = None

# Miniforge / conda-forge Python ships tcl/tk under Library\bin and
# Library\lib. PyInstaller's stock tkinter hook does not find them there
# (it assumes a standard CPython layout), so the build succeeds but the
# resulting exe crashes with "DLL load failed while importing _tkinter:
# tcl86t.dll" the moment the GUI starts. We include them explicitly here.
_CONDA_ROOT = r'D:\025.Miniforge'
_TCL_TK_BINARIES = [
    (_CONDA_ROOT + r'\Library\bin\tcl86t.dll', '.'),
    (_CONDA_ROOT + r'\Library\bin\tk86t.dll',  '.'),
]
_TCL_TK_DATAS = [
    (_CONDA_ROOT + r'\Library\lib\tcl8.6', 'tcl8.6'),
    (_CONDA_ROOT + r'\Library\lib\tk8.6',  'tk8.6'),
]

a = Analysis(
    ['scripts/ui_app.py'],
    pathex=['.'],
    binaries=_TCL_TK_BINARIES,
    datas=_TCL_TK_DATAS,
    hiddenimports=[
        # pip deps — PyInstaller usually finds these, but declare for safety
        'pymysql',
        'pymysql.cursors',
        'psycopg2',
        # oracledb exposes Python-side dialect hooks; PyInstaller discovers
        # the top-level package, but the thin-mode implementation imports
        # submodules dynamically at connect() time — list them explicitly.
        'oracledb',
        'oracledb.thin_impl',
        'sqlalchemy',
        # SQLAlchemy resolves dialect modules via entry points at runtime.
        # PyInstaller sometimes misses these, so pin them explicitly.
        'sqlalchemy.dialects.mysql',
        'sqlalchemy.dialects.mysql.pymysql',
        'sqlalchemy.dialects.postgresql',
        'sqlalchemy.dialects.postgresql.psycopg2',
        'sqlalchemy.dialects.oracle',
        'sqlalchemy.dialects.oracle.oracledb',
        'sqlalchemy.dialects.sqlite',
        'sqlalchemy.dialects.sqlite.pysqlite',
        # sqlite3 is stdlib but the dbapi hook for SQLAlchemy wants it explicit
        'sqlite3',
        'loguru',
        'dotenv',
        'tabulate',
        'tqdm',
        'dateutil',
        # first-party — static imports should be sufficient, listed for clarity
        'src.ui.main_window',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # heavy packages not used by GUI — shrink bundle
        'numpy',
        'pandas',
        'matplotlib',
        'scipy',
        'IPython',
        'jupyter',
        'notebook',
        'pytest',
    ],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='mysql_factory',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,     # keep console for now — flip to False once stable
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='mysql_factory',
)
