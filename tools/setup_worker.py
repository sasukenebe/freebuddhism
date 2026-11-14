#!/usr/bin/env python3
# SPDX-License-Identifier: 0BSD
"""Prepare a pinned worker checkout over existing SSH access; no build or deploy."""
from __future__ import annotations

import argparse
from pathlib import Path, PurePosixPath
import re
import shlex
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SOURCE_URL = "https://github.com/sasukenebe/freebuddhism.git"
REMOTE_SETUP = r'''
set -eu
repo=$1
revision=$2
payload=$3
source_url=$4
install_system=$5
command -v git >/dev/null || { echo "Install Git on the worker before cloning" >&2; exit 1; }
command -v python3 >/dev/null || { echo "Python 3.12+ is required on the worker" >&2; exit 1; }
python3 -c 'from pathlib import Path; import sys; p=Path(sys.argv[1]); sys.exit("Linked checkout paths are not allowed" if any(x.is_symlink() for x in [p,*p.parents]) else 0)' "$repo"
if [ -e "$repo" ] || [ -L "$repo" ]; then
  [ ! -L "$repo" ] && [ -d "$repo/.git" ] || { echo "Refusing an existing non-checkout or linked destination" >&2; exit 1; }
  [ "$(git -C "$repo" rev-parse --show-toplevel)" = "$repo" ] || exit 1
  [ "$(git -C "$repo" remote get-url origin)" = "$source_url" ] || { echo "Worker repository origin differs" >&2; exit 1; }
  [ -z "$(git -C "$repo" status --porcelain)" ] || { echo "Worker checkout has local changes; left unchanged" >&2; exit 1; }
  [ "$(git -C "$repo" rev-parse HEAD)" = "$revision" ] || { echo "Worker checkout is at another revision; left unchanged" >&2; exit 1; }
else
  mkdir -p "$(dirname "$repo")"
  git clone --no-checkout "$source_url" "$repo"
  git -C "$repo" checkout --detach "$revision"
fi
[ "$(git -C "$repo" rev-parse HEAD)" = "$revision" ] || exit 1
set -- python3 "$payload/bootstrap.py" --project-root "$repo" --system-requirements "$payload/requirements-system.txt"
if [ "$install_system" = yes ]; then set -- "$@" --install-system; fi
exec "$@"
'''


def validate_target(host: str, destination: str, revision: str) -> None:
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]*", host):
        raise ValueError("Use a saved SSH alias or hostname, not options or a numeric-address fallback")
    path = PurePosixPath(destination)
    if (not path.is_absolute() or len(path.parts) < 3 or ".." in path.parts
            or str(path) != destination or "\x00" in destination or "\n" in destination):
        raise ValueError("Use an explicit absolute worker checkout path, not a broad directory")
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("Pin a complete 40-character source commit")


def setup(host: str, destination: str, revision: str, *, install=False) -> None:
    validate_target(host, destination, revision)
    if install and not sys.stdin.isatty():
        raise ValueError("Run --install-system from a terminal so the worker can request sudo authorization")
    for program in ("ssh", "scp"):
        if shutil.which(program) is None:
            raise ValueError("Missing local command: " + program)
    files = [ROOT / "tools/bootstrap.py", ROOT / "requirements-system.txt"]
    if any(not p.is_file() or p.is_symlink() for p in files):
        raise ValueError("Local bootstrap inputs are missing or linked")
    connection = ["-o", "ConnectTimeout=25", "-o", "StrictHostKeyChecking=yes", "-o", "ForwardAgent=no"]
    # Only original setup code/config is staged. No Git credentials, private PDFs,
    # correspondence, other local edits or entire working-directory copies.
    result = subprocess.run(["ssh", *connection, "-o", "BatchMode=yes", host,
                             "umask 077; mktemp -d /tmp/freebuddhism-bootstrap.XXXXXXXX"],
                            check=True, capture_output=True, text=True)
    payload = result.stdout.strip()
    if not re.fullmatch(r"/tmp/freebuddhism-bootstrap\.[A-Za-z0-9]{8}", payload):
        raise ValueError("Unexpected worker staging path")
    print("Worker setup files retained at " + payload, flush=True)
    subprocess.run(["scp", *connection, "--", *(str(p) for p in files), host + ":" + payload + "/"], check=True)
    command = shlex.join(["sh", "-c", REMOTE_SETUP, "worker-setup", destination,
                          revision, payload, SOURCE_URL, "yes" if install else "no"])
    subprocess.run(["ssh", *connection, *(["-t"] if install else []), host, command], check=True)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True, help="Existing SSH alias with a verified host key")
    parser.add_argument("--destination", required=True, help="Dedicated absolute worker checkout path")
    parser.add_argument("--revision", required=True, help="Exact published source commit")
    parser.add_argument("--install-system", action="store_true", help="Ask the worker to install native packages through sudo")
    args = parser.parse_args(argv)
    try:
        setup(args.host, args.destination, args.revision, install=args.install_system)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print("Worker setup failed: " + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
