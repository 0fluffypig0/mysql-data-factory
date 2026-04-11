#!/usr/bin/env python3
"""
MySQL Data Factory 3.0 — 离线环境构建脚本。

当前方案：
1. 下载 Python Embeddable Package (Windows x64)
2. 额外准备一个同版本的完整 CPython，仅用于提取 tkinter / Tcl / Tk 运行时
3. 安装 pip 到 embeddable Python
4. 下载所有依赖 wheel 到 vendor/
5. 打包成一个 zip，可带到堡垒机离线部署

这样可以同时保留：
- CLI 的小体积
- GUI 的 tkinter 运行能力
- 仍然不依赖 conda-pack
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

PYTHON_EMBED_URL = "https://www.python.org/ftp/python/{version}/python-{version}-embed-amd64.zip"
PYTHON_INSTALLER_URL = "https://www.python.org/ftp/python/{version}/python-{version}-amd64.exe"
GET_PIP_URL = "https://bootstrap.pypa.io/get-pip.py"


def download_file(url: str, dest: Path) -> None:
    """下载文件到指定路径。"""
    print(f"[DOWNLOAD] {url}")
    print(f"        -> {dest}")
    urllib.request.urlretrieve(url, str(dest))
    size_mb = dest.stat().st_size / (1024 * 1024)
    print(f"        OK ({size_mb:.1f} MB)")


def run_checked(cmd: list[str], cwd: Path | None = None) -> None:
    """Run a command with readable console output."""
    print(f"[RUN] {' '.join(cmd)}")
    subprocess.run(cmd, cwd=str(cwd) if cwd else None, check=True)


def major_minor(version: str) -> str:
    """Return major.minor for a full version string."""
    parts = version.split(".")
    return ".".join(parts[:2])


def python_version_mm(python_exe: Path) -> str:
    """Query a Python executable for its major.minor version."""
    result = subprocess.run(
        [str(python_exe), "-c", "import sys; print(f'{sys.version_info[0]}.{sys.version_info[1]}')"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def enable_embed_lib_imports(pth_file: Path) -> None:
    """Enable import site and make Lib/ importable in the embeddable runtime."""
    original_lines = pth_file.read_text(encoding="utf-8").splitlines()
    normalized = [line.strip() for line in original_lines]

    output_lines: list[str] = []
    inserted = False
    for line in original_lines:
        stripped = line.strip()
        if stripped in {"#import site", "import site"}:
            if "Lib" not in normalized:
                output_lines.append("Lib")
            if "Lib\\site-packages" not in normalized:
                output_lines.append("Lib\\site-packages")
            output_lines.append("import site")
            inserted = True
        else:
            output_lines.append(line)

    if not inserted:
        if "Lib" not in normalized:
            output_lines.append("Lib")
        if "Lib\\site-packages" not in normalized:
            output_lines.append("Lib\\site-packages")
        output_lines.append("import site")

    pth_file.write_text("\n".join(output_lines) + "\n", encoding="utf-8")


def install_full_python_for_tk(version: str, work_dir: Path) -> Path:
    """Install the official CPython runtime into a temp directory to harvest Tk assets."""
    print()
    print("=" * 50)
    print("Step 1.5: Install Full Python Runtime For Tk")
    print("=" * 50)

    installer_exe = work_dir / f"python-{version}-amd64.exe"
    download_file(PYTHON_INSTALLER_URL.format(version=version), installer_exe)

    full_python_dir = work_dir / f"python-full-{version}"
    if full_python_dir.exists():
        shutil.rmtree(full_python_dir)
    full_python_dir.mkdir(parents=True)

    run_checked([
        str(installer_exe),
        "/quiet",
        f"TargetDir={full_python_dir}",
        "InstallAllUsers=0",
        "PrependPath=0",
        "Shortcuts=0",
        "AssociateFiles=0",
        "CompileAll=0",
        "Include_doc=0",
        "Include_test=0",
        "Include_launcher=0",
        "Include_pip=0",
        "Include_tcltk=1",
        "SimpleInstall=1",
    ])

    python_exe = full_python_dir / "python.exe"
    if not python_exe.exists():
        raise RuntimeError(f"Full Python install did not produce python.exe at {python_exe}")

    print(f"[OK] Installed full Python runtime to {full_python_dir}")
    return python_exe


def discover_tk_assets(python_exe: Path) -> dict[str, str]:
    """Query a Python runtime for the files needed by tkinter."""
    helper = """
import json
import pathlib
import sys
import tkinter
import _tkinter

interp = tkinter.Tcl()
base = pathlib.Path(sys.base_prefix).resolve()
tcl_lib = pathlib.Path(interp.eval("info library")).resolve()
tk_lib = tcl_lib.parent / ("tk" + tcl_lib.name[3:])
if not tk_lib.exists():
    candidates = sorted(p for p in tcl_lib.parent.glob("tk*") if p.is_dir())
    if candidates:
        tk_lib = candidates[0]

dll_names = ["tcl86t.dll", "tk86t.dll", "tcldde14.dll", "tclreg13.dll"]
dll_map = {}
for name in dll_names:
    matches = list(base.rglob(name))
    if matches:
        dll_map[name] = str(matches[0].resolve())

payload = {
    "base_prefix": str(base),
    "tkinter_pkg": str(pathlib.Path(tkinter.__file__).resolve().parent),
    "_tkinter_pyd": str(pathlib.Path(_tkinter.__file__).resolve()),
    "tcl_lib": str(tcl_lib),
    "tk_lib": str(tk_lib) if tk_lib.exists() else "",
    "tcl_dll": dll_map.get("tcl86t.dll", ""),
    "tk_dll": dll_map.get("tk86t.dll", ""),
    "tcldde_dll": dll_map.get("tcldde14.dll", ""),
    "tclreg_dll": dll_map.get("tclreg13.dll", ""),
}
print(json.dumps(payload))
""".strip()

    result = subprocess.run(
        [str(python_exe), "-c", helper],
        check=True,
        capture_output=True,
        text=True,
    )
    data = json.loads(result.stdout.strip())

    required = ["tkinter_pkg", "_tkinter_pyd", "tcl_lib", "tk_lib", "tcl_dll", "tk_dll"]
    missing = [key for key in required if not data.get(key)]
    if missing:
        raise RuntimeError(f"tk asset discovery incomplete for {python_exe}: missing {missing}")

    return data


def copy_optional_file(src: str, dest_dir: Path) -> None:
    """Copy an optional file when it exists."""
    if not src:
        return
    src_path = Path(src)
    if not src_path.exists():
        return
    dest_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src_path, dest_dir / src_path.name)


def copy_dir(src: Path, dest: Path) -> None:
    """Replace a directory with a fresh copy."""
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest)


def copy_tk_assets(source_python: Path, target_python_dir: Path) -> None:
    """Copy tkinter, Tcl, and Tk runtime files into the embeddable package."""
    print()
    print("=" * 50)
    print("Step 1.6: Copy Tkinter / Tcl / Tk Assets")
    print("=" * 50)

    tk_assets = discover_tk_assets(source_python)

    lib_dir = target_python_dir / "Lib"
    lib_dir.mkdir(parents=True, exist_ok=True)

    copy_dir(Path(tk_assets["tkinter_pkg"]), lib_dir / "tkinter")
    shutil.copy2(Path(tk_assets["_tkinter_pyd"]), target_python_dir / "_tkinter.pyd")
    copy_optional_file(tk_assets["tcl_dll"], target_python_dir)
    copy_optional_file(tk_assets["tk_dll"], target_python_dir)

    tcl_root = target_python_dir / "tcl"
    tcl_root.mkdir(parents=True, exist_ok=True)

    tcl_lib = Path(tk_assets["tcl_lib"])
    tk_lib = Path(tk_assets["tk_lib"])
    copy_dir(tcl_lib, tcl_root / tcl_lib.name)
    copy_dir(tk_lib, tcl_root / tk_lib.name)

    for extra_dir_name in ["dde1.4", "reg1.3"]:
        extra_src = tcl_lib.parent / extra_dir_name
        if extra_src.exists():
            copy_dir(extra_src, tcl_root / extra_dir_name)
    copy_optional_file(tk_assets.get("tcldde_dll", ""), tcl_root / "dde1.4")
    copy_optional_file(tk_assets.get("tclreg_dll", ""), tcl_root / "reg1.3")

    sitecustomize = (
        "from __future__ import annotations\n"
        "import os\n"
        "from pathlib import Path\n\n"
        "_ROOT = Path(__file__).resolve().parent\n"
        "_TCL = _ROOT / 'tcl' / 'tcl8.6'\n"
        "_TK = _ROOT / 'tcl' / 'tk8.6'\n"
        "if _TCL.exists():\n"
        "    os.environ.setdefault('TCL_LIBRARY', str(_TCL))\n"
        "if _TK.exists():\n"
        "    os.environ.setdefault('TK_LIBRARY', str(_TK))\n"
    )
    (target_python_dir / "sitecustomize.py").write_text(sitecustomize, encoding="utf-8")

    print(f"[OK] tkinter package copied from {tk_assets['tkinter_pkg']}")
    print(f"[OK] Tcl library copied from {tcl_lib}")
    print(f"[OK] Tk library copied from {tk_lib}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build offline deployment package for mysql-data-factory 3.0.",
    )
    parser.add_argument(
        "--python-version",
        default="3.11.9",
        help="Python embeddable version to download (default: 3.11.9)",
    )
    parser.add_argument(
        "--output-dir",
        default=str(PROJECT_ROOT / "env_export"),
        help="Output directory for the deployment package",
    )
    parser.add_argument(
        "--requirements",
        default=str(PROJECT_ROOT / "requirements.txt"),
        help="Path to requirements.txt",
    )
    parser.add_argument(
        "--tk-source-python",
        default="",
        help=(
            "Optional path to a full Python executable with tkinter matching --python-version. "
            "If omitted, the script installs an official CPython runtime temporarily and harvests Tk assets from it."
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    requirements_file = Path(args.requirements).resolve()
    output_dir = Path(args.output_dir).resolve()
    python_version = args.python_version

    if not requirements_file.exists():
        print(f"[ERROR] requirements file not found: {requirements_file}")
        return 1

    work_dir = PROJECT_ROOT / ".build_tmp"
    if work_dir.exists():
        shutil.rmtree(work_dir)
    work_dir.mkdir(parents=True)

    try:
        print()
        print("=" * 50)
        print("Step 1: Download Python Embeddable Package")
        print("=" * 50)

        embed_url = PYTHON_EMBED_URL.format(version=python_version)
        embed_zip = work_dir / f"python-{python_version}-embed-amd64.zip"
        download_file(embed_url, embed_zip)

        python_dir = work_dir / "python"
        python_dir.mkdir()
        with zipfile.ZipFile(embed_zip, "r") as zf:
            zf.extractall(python_dir)
        print(f"[OK] Extracted to {python_dir}")

        pth_files = list(python_dir.glob("python*._pth"))
        if pth_files:
            enable_embed_lib_imports(pth_files[0])
            print(f"[OK] Enabled site-packages and Lib imports in {pth_files[0].name}")

        python_exe = python_dir / "python.exe"
        if not python_exe.exists():
            print("[ERROR] python.exe not found in embeddable package")
            return 1

        tk_source_python = Path(args.tk_source_python).resolve() if args.tk_source_python else None
        if tk_source_python is not None:
            if not tk_source_python.exists():
                print(f"[ERROR] Tk source Python not found: {tk_source_python}")
                return 1
            source_mm = python_version_mm(tk_source_python)
            target_mm = major_minor(python_version)
            if source_mm != target_mm:
                print(f"[ERROR] Tk source Python version mismatch: source={source_mm}, target={target_mm}")
                return 1
        else:
            tk_source_python = install_full_python_for_tk(python_version, work_dir)

        copy_tk_assets(tk_source_python, python_dir)

        print()
        print("=" * 50)
        print("Step 2: Install pip into embeddable Python")
        print("=" * 50)

        get_pip = work_dir / "get-pip.py"
        download_file(GET_PIP_URL, get_pip)

        run_checked(
            [str(python_exe), str(get_pip), "--no-warn-script-location"],
            cwd=python_dir,
        )
        print("[OK] pip installed")

        print()
        print("=" * 50)
        print("Step 3: Download wheels for all dependencies")
        print("=" * 50)

        vendor_dir = work_dir / "vendor"
        vendor_dir.mkdir()

        subprocess.run(
            [
                str(python_exe),
                "-m",
                "pip",
                "download",
                "-r",
                str(requirements_file),
                "-d",
                str(vendor_dir),
                "--only-binary=:all:",
                "--platform=win_amd64",
                "--python-version",
                major_minor(python_version),
            ],
            check=False,
        )
        run_checked(
            [str(python_exe), "-m", "pip", "download", "-r", str(requirements_file), "-d", str(vendor_dir)]
        )
        wheel_count = len(list(vendor_dir.glob("*")))
        print(f"[OK] Downloaded {wheel_count} packages to vendor/")

        print()
        print("=" * 50)
        print("Step 4: Assemble deployment package")
        print("=" * 50)

        deploy_dir = work_dir / "mysql_factory_env"
        deploy_dir.mkdir()

        shutil.copytree(python_dir, deploy_dir / "python")
        shutil.copytree(vendor_dir, deploy_dir / "vendor")

        install_bat = deploy_dir / "install.bat"
        install_bat.write_text(
            '@echo off\n'
            'chcp 65001 >nul\n'
            'echo Installing dependencies from vendor...\n'
            'set "PYTHON=%~dp0python\\python.exe"\n'
            'set "TCL_LIBRARY=%~dp0python\\tcl\\tcl8.6"\n'
            'set "TK_LIBRARY=%~dp0python\\tcl\\tk8.6"\n'
            '"%PYTHON%" -m pip install --no-index --find-links="%~dp0vendor" '
            '-r "%~dp0..\\requirements.txt" --no-warn-script-location\n'
            'if errorlevel 1 (\n'
            '    echo [ERROR] Installation failed.\n'
            '    exit /b 1\n'
            ')\n'
            'echo [OK] All dependencies installed.\n'
            '"%PYTHON%" --version\n'
            '"%PYTHON%" -c "import pymysql, tkinter as tk; print(\'pymysql OK\'); print(tk.Tcl().eval(\'info library\'))"\n',
            encoding="utf-8",
        )

        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / "mysql_factory_env.zip"
        if output_file.exists():
            output_file.unlink()

        print(f"[PACK] Creating {output_file}...")
        with zipfile.ZipFile(output_file, "w", zipfile.ZIP_DEFLATED) as zf:
            for file_path in deploy_dir.rglob("*"):
                if file_path.is_file():
                    arcname = file_path.relative_to(deploy_dir.parent)
                    zf.write(file_path, arcname)

        size_mb = output_file.stat().st_size / (1024 * 1024)

        print()
        print("=" * 50)
        print("Build complete!")
        print("=" * 50)
        print(f"Output: {output_file}")
        print(f"Size: {size_mb:.1f} MB")
        print(f"Python: {python_version} (embeddable + tkinter)")
        print()
        print("Next steps:")
        print("  1. Copy the whole project folder plus env_export/ to the bastion host")
        print("  2. Run bin\\setup_offline.bat")
        print("  3. Run bin\\test_connection.bat")
        print("  4. Run bin\\run_gui.bat")
        return 0

    except Exception as exc:
        print(f"[ERROR] {exc}")
        return 1
    finally:
        if work_dir.exists():
            shutil.rmtree(work_dir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
