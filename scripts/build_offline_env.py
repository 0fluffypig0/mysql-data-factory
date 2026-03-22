#!/usr/bin/env python3
"""Build the minimal offline runtime package for the bastion host workflow."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONDA_EXE = Path(sys.executable).resolve().parent / "condabin" / "conda.bat"


def run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    print(f"[RUN] {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=PROJECT_ROOT, text=True)
    if check and result.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}")
    return result


def conda_command(conda_exe: Path, *args: str) -> list[str]:
    if conda_exe.suffix.lower() == ".bat":
        return ["cmd.exe", "/d", "/c", str(conda_exe), *args]
    return [str(conda_exe), *args]


def conda_env_exists(conda_exe: Path, env_prefix: Path) -> bool:
    result = subprocess.run(
        conda_command(conda_exe, "run", "-p", str(env_prefix), "python", "--version"),
        cwd=PROJECT_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    return result.returncode == 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a minimal conda-pack offline environment for mysql-data-factory.",
    )
    parser.add_argument("--env-name", default="mysql_factory")
    parser.add_argument(
        "--env-prefix",
        default="",
        help="Optional explicit conda environment prefix. Defaults to .offline_envs/<env-name> under the repo.",
    )
    parser.add_argument("--python-version", default="3.10")
    parser.add_argument("--output-dir", default=str(PROJECT_ROOT / "env_export"))
    parser.add_argument("--requirements", default=str(PROJECT_ROOT / "requirements.txt"))
    parser.add_argument("--conda-exe", default=str(DEFAULT_CONDA_EXE))
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Remove the target conda environment first if it already exists.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    requirements_file = Path(args.requirements).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_file = output_dir / f"{args.env_name}_env.tar.gz"
    conda_exe = Path(args.conda_exe).resolve()
    env_prefix = Path(args.env_prefix).resolve() if args.env_prefix else (PROJECT_ROOT / ".offline_envs" / args.env_name)

    if not requirements_file.exists():
        print(f"[ERROR] requirements file not found: {requirements_file}")
        return 1
    if not conda_exe.exists():
        print(f"[ERROR] conda executable not found: {conda_exe}")
        return 1

    try:
        run(conda_command(conda_exe, "--version"))

        if args.rebuild and conda_env_exists(conda_exe, env_prefix):
            run(conda_command(conda_exe, "remove", "-p", str(env_prefix), "--all", "-y"))

        if not conda_env_exists(conda_exe, env_prefix):
            env_prefix.parent.mkdir(parents=True, exist_ok=True)
            run(
                conda_command(
                    conda_exe,
                    "create",
                    "-p",
                    str(env_prefix),
                    f"python={args.python_version}",
                    "pip",
                    "-y",
                )
            )
        else:
            print(f"[INFO] Reusing existing conda environment: {env_prefix}")

        run(
            conda_command(
                conda_exe,
                "run",
                "-p",
                str(env_prefix),
                "python",
                "-m",
                "pip",
                "install",
                "-r",
                str(requirements_file),
            )
        )
        run(
            conda_command(
                conda_exe,
                "run",
                "-p",
                str(env_prefix),
                "python",
                "-m",
                "pip",
                "install",
                "conda-pack",
            )
        )

        output_dir.mkdir(parents=True, exist_ok=True)
        if output_file.exists():
            output_file.unlink()

        run(
            conda_command(
                conda_exe,
                "run",
                "-p",
                str(env_prefix),
                "python",
                "-m",
                "conda_pack.cli",
                "-p",
                str(env_prefix),
                "-o",
                str(output_file),
                "--force",
            )
        )

        if not output_file.exists():
            print(f"[ERROR] output file was not created: {output_file}")
            return 1

        size_mb = output_file.stat().st_size / (1024 * 1024)
        print()
        print("Build complete.")
        print(f"Environment prefix: {env_prefix}")
        print(f"Output: {output_file}")
        print(f"Size: {size_mb:.2f} MB")
        print("Next step: copy the repository plus env_export/ to the bastion host and run bin\\setup_offline.bat.")
        return 0
    except RuntimeError as exc:
        print(f"[ERROR] {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
