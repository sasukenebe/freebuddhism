#!/usr/bin/env python3
# SPDX-License-Identifier: 0BSD
"""Set up or check an isolated build environment; never build, import or deploy."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
MARKER = {"schema": 1, "kind": "freebuddhism-build-environment"}
TOOLS = {"git": "--version", "pdfinfo": "-v", "pdftotext": "-v", "mutool": "-v"}


class SetupError(RuntimeError):
    pass


def run(command, **kwargs):
    return subprocess.run(command, check=True, **kwargs)


def python_requirements(path: Path) -> dict[str, str]:
    result = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.fullmatch(r"([A-Za-z0-9][A-Za-z0-9_.-]*)==([A-Za-z0-9_.+!-]+)", line)
        if not match:
            raise SetupError("Use exact name==version pins in requirements.txt")
        name = re.sub(r"[-_.]+", "-", match[1]).lower()
        if name in result:
            raise SetupError("Duplicate Python requirement: " + name)
        result[name] = match[2]
    if not result:
        raise SetupError("Python requirements must not be empty")
    return result


def system_requirements(path: Path) -> list[str]:
    packages = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip() and not line.lstrip().startswith("#")]
    if (not packages or len(set(packages)) != len(packages)
            or any(not re.fullmatch(r"[a-z0-9][a-z0-9+.-]*", p) for p in packages)):
        raise SetupError("Use one distinct Debian package name per system-requirements line")
    return packages


def checked_environment(root: Path) -> Path:
    env = root / ".venv"
    if env.is_symlink() or getattr(env, "is_junction", lambda: False)():
        raise SetupError("Refusing a linked virtual-environment directory")
    if env.exists():
        marker = env / ".freebuddhism-bootstrap.json"
        if (not env.is_dir() or marker.is_symlink() or not marker.is_file()
                or json.loads(marker.read_text(encoding="utf-8")) != MARKER):
            raise SetupError("Existing .venv is not owned by this bootstrap; it was left unchanged")
    return env


def environment_python(env: Path) -> Path:
    return env / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def system_problems() -> list[str]:
    problems = []
    for program, option in TOOLS.items():
        if shutil.which(program) is None:
            problems.append("Missing native tool: " + program)
            continue
        result = subprocess.run([program, option], capture_output=True, text=True)
        if result.returncode:
            problems.append("Native tool cannot run: " + program)
    if shutil.which("fc-match") is None:
        problems.append("Missing native tool: fc-match")
    else:
        for style in ("Regular", "Bold"):
            result = subprocess.run(["fc-match", "-f", "%{family}|%{style}", "Noto Sans:style=" + style],
                                    capture_output=True, text=True)
            family, separator, actual_style = result.stdout.partition("|")
            if (result.returncode or not separator or "Noto Sans" not in family.split(",")
                    or style.lower() not in actual_style.lower()):
                problems.append("Missing Noto Sans " + style + " font (fallback fonts do not count)")
    return problems


def install_system(packages: list[str]) -> None:
    if sys.platform != "linux":
        raise SetupError("Automatic system installation supports Debian/Ubuntu Linux only")
    distro = platform.freedesktop_os_release()
    if not {distro.get("ID", ""), *distro.get("ID_LIKE", "").split()} & {"debian", "ubuntu"}:
        raise SetupError("Install the documented native tools/fonts using your OS package manager")
    if shutil.which("apt-get") is None:
        raise SetupError("apt-get is required for --install-system")
    prefix = [] if os.geteuid() == 0 else ["sudo"]
    if prefix and shutil.which("sudo") is None:
        raise SetupError("sudo is required for --install-system; no system changes made")
    print("Explicit system install: " + ", ".join(packages), flush=True)
    run(prefix + ["apt-get", "update"])
    run(prefix + ["apt-get", "install", "--no-install-recommends", "-y", *packages])


def create_environment(env: Path) -> Path:
    if not env.exists():
        env.mkdir()
        with (env / ".freebuddhism-bootstrap.json").open("x", encoding="utf-8") as marker:
            json.dump(MARKER, marker)
            marker.write("\n")
    python = environment_python(env)
    if not python.is_file():
        # Failed/interrupted creation stays marked and can be retried, never deleted.
        run([sys.executable, "-m", "venv", str(env)])
    return python


def ensure_pip(python: Path) -> None:
    result = subprocess.run([str(python), "-m", "pip", "--version"], capture_output=True, text=True)
    if result.returncode:
        run([str(python), "-m", "ensurepip", "--upgrade"])


def environment_problems(python: Path, pins: dict[str, str]) -> list[str]:
    if not python.is_file():
        return ["Missing managed virtual environment; run bootstrap without --check"]
    program = """
import importlib.metadata as m, json, sys
packages = {}
for name in json.loads(sys.argv[1]):
    try: packages[name] = m.version(name)
    except m.PackageNotFoundError: packages[name] = None
print(json.dumps({'isolated': sys.prefix != sys.base_prefix,
                  'python': list(sys.version_info[:2]), 'packages': packages}))
"""
    result = subprocess.run([str(python), "-c", program, json.dumps(list(pins))],
                            capture_output=True, text=True)
    if result.returncode:
        return ["Managed Python cannot inspect its package versions"]
    report = json.loads(result.stdout)
    problems = []
    config = python.parent.parent / "pyvenv.cfg"
    if (not report["isolated"] or not config.is_file()
            or re.search(r"include-system-site-packages\s*=\s*true", config.read_text(), re.I)):
        problems.append("Virtual environment is not isolated from system packages")
    if report["python"] < [3, 12]:
        problems.append("Managed environment needs Python 3.12 or newer")
    for name, version in pins.items():
        if report["packages"].get(name) != version:
            problems.append(f"Expected {name}=={version}; found {report['packages'].get(name)}")
    return problems


def bootstrap(root: Path, system_file: Path, *, check=False, install=False) -> dict:
    if sys.version_info < (3, 12):
        raise SetupError("Run this bootstrap with Python 3.12 or newer")
    root = root.resolve()
    requirements = root / "requirements.txt"
    pins = python_requirements(requirements)
    packages = system_requirements(system_file)
    env = checked_environment(root)  # Refuse foreign environments before any package install.
    if environment_python(env).is_file():
        identity_problems = environment_problems(environment_python(env), {})
        if identity_problems:
            raise SetupError("\n".join(identity_problems))
    if install:
        install_system(packages)
    problems = system_problems()
    if check:
        problems.extend(environment_problems(environment_python(env), pins))
    if problems:
        raise SetupError("\n".join(problems) +
                         "\nOn Ubuntu/Debian, rerun with --install-system for native dependencies.")
    if not check:
        python = create_environment(env)
        problems = environment_problems(python, {})
        if problems:
            raise SetupError("\n".join(problems))
        ensure_pip(python)  # Resume an interrupted managed environment without deleting it.
        run([str(python), "-m", "pip", "--disable-pip-version-check", "install",
             "--only-binary=:all:", "-r", str(requirements)])
        problems = environment_problems(python, pins)
        if problems:
            raise SetupError("\n".join(problems))
    run([str(environment_python(env)), "-m", "pip", "check"])
    return {"status": "READY", "python": str(environment_python(env)),
            "pinned_packages": pins, "native_tools_and_fonts": "PASS",
            "scope": "Build environment only; no source import, build or deployment performed"}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=ROOT,
                        help="Requirements/venv destination; also supports a separately staged bootstrap")
    parser.add_argument("--system-requirements", type=Path, default=ROOT / "requirements-system.txt")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--check", action="store_true", help="Read-only dependency check; never installs")
    group.add_argument("--install-system", action="store_true", help="Explicitly install Debian/Ubuntu packages using apt/sudo")
    args = parser.parse_args(argv)
    try:
        report = bootstrap(args.project_root, args.system_requirements, check=args.check, install=args.install_system)
    except (SetupError, OSError, ValueError, subprocess.CalledProcessError) as error:
        print("Bootstrap failed: " + str(error), file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
