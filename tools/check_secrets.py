#!/usr/bin/env python3
"""Run the same pinned, redacted history scan locally and in GitHub Actions."""

from __future__ import annotations

import hashlib
import io
import os
from pathlib import Path
import platform
import subprocess
import sys
import tarfile
import tempfile
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
VERSION = "8.30.1"
ARCHIVE_URL = (
    f"https://github.com/gitleaks/gitleaks/releases/download/v{VERSION}/"
    f"gitleaks_{VERSION}_linux_x64.tar.gz"
)
ARCHIVE_SHA256 = "551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb"
MAX_DOWNLOAD_BYTES = 64 * 1024 * 1024


def verified_binary(archive_bytes: bytes) -> bytes:
    if hashlib.sha256(archive_bytes).hexdigest() != ARCHIVE_SHA256:
        raise ValueError("Gitleaks archive checksum mismatch; refusing to execute it")
    with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:gz") as archive:
        members = [member for member in archive.getmembers() if member.name == "gitleaks"]
        if (len(members) != 1 or not members[0].isfile()
                or not 0 < members[0].size <= MAX_DOWNLOAD_BYTES):
            raise ValueError("Gitleaks archive must contain one regular executable")
        with archive.extractfile(members[0]) as stream:
            binary = stream.read(MAX_DOWNLOAD_BYTES + 1)
        if len(binary) != members[0].size:
            raise ValueError("Gitleaks executable is truncated")
        return binary


def atomic_write(path: Path, data: bytes, mode: int) -> None:
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.chmod(mode)
        temporary.replace(path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def ensure_scanner(cache: Path | None = None) -> Path:
    if platform.system() != "Linux" or platform.machine().lower() not in {"x86_64", "amd64"}:
        raise ValueError("The pinned scanner supports Linux x86-64; add a verified asset for this platform")
    cache = cache if cache is not None else ROOT / "build" / "security-tools" / f"gitleaks-{VERSION}"
    for path in (ROOT / "build", cache.parent, cache):
        if path.is_symlink():
            raise ValueError("Refusing a symlinked scanner cache")
    cache.mkdir(parents=True, exist_ok=True)
    archive = cache / "release.tar.gz"
    executable = cache / "gitleaks"
    if archive.is_symlink() or executable.is_symlink():
        raise ValueError("Refusing a symlinked scanner asset")
    if archive.exists():
        archive_bytes = archive.read_bytes()
        binary = verified_binary(archive_bytes)
    else:
        with urlopen(ARCHIVE_URL, timeout=60) as response:
            archive_bytes = response.read(MAX_DOWNLOAD_BYTES + 1)
        if len(archive_bytes) > MAX_DOWNLOAD_BYTES:
            raise ValueError("Gitleaks download exceeds its size limit")
        binary = verified_binary(archive_bytes)
        atomic_write(archive, archive_bytes, 0o600)
    # Recheck the archive on every invocation and repair a changed cached executable.
    if not executable.is_file() or executable.read_bytes() != binary:
        atomic_write(executable, binary, 0o700)
    executable.chmod(0o700)
    return executable


def scan(repository: Path, executable: Path) -> int:
    shallow = subprocess.run(
        ["git", "rev-parse", "--is-shallow-repository"], cwd=repository,
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    if shallow != "false":
        raise ValueError("Secret scan requires complete history; fetch with depth 0 or unshallow first")
    environment = {key: value for key, value in os.environ.items()
                   if key not in {"GITLEAKS_CONFIG", "GITLEAKS_CONFIG_TOML"}}
    # Ignore local suppression files and inline bypass comments; keep all scanner output redacted.
    command = [str(executable), "git", "--redact=100", "--no-banner", "--no-color",
               "--ignore-gitleaks-allow", "--gitleaks-ignore-path", str(executable.parent),
               "--log-opts=--all", "--max-archive-depth=2", "--max-decode-depth=5", str(repository)]
    return subprocess.run(command, cwd=repository, env=environment, check=False).returncode


def main() -> int:
    try:
        return scan(ROOT, ensure_scanner())
    except (OSError, ValueError, tarfile.TarError, subprocess.CalledProcessError) as error:
        print(f"Secret scan failed: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
