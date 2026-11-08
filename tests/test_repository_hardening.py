import hashlib
import io
import os
from pathlib import Path
import re
import secrets
import shutil
import string
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import check_secrets  # noqa: E402
from validate_public_tree import actual_files, license_scope_for  # noqa: E402


class RepositoryHardeningTests(unittest.TestCase):
    def test_secret_names_are_ignored_but_sanitized_examples_are_not(self):
        ignored = {".env", "nested/.env.production", "deploy/credentials.json",
                   "deploy/credentials.dev.json", "tls/private.key", "tls/private.pem",
                   "tls/archive.p12", "keys/id_ed25519", "private/.secrets/token",
                   "config.local.json", "deploy/service-account-prod.json", "local.env"}
        examples = {".env.example", ".env.production.example", "nested/.env.sample",
                    "nested/.env.production.template", "README.md", "metadata/eligible-texts.json"}
        result = subprocess.run(
            ["git", "check-ignore", "--no-index", "--stdin"], cwd=ROOT,
            input="\n".join(sorted(ignored | examples)) + "\n", capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(set(result.stdout.splitlines()), ignored)

    def test_git_ignore_does_not_exempt_secret_files_from_publication_policy(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / ".env").write_text("not a credential\n", encoding="utf-8")
            self.assertIn(".env", actual_files(root))
            with self.assertRaisesRegex(ValueError, "No exact approved rights entry"):
                license_scope_for(".env", {})

    def test_workflow_has_pinned_read_only_checks_and_no_deployment(self):
        workflow = (ROOT / ".github/workflows/validate.yml").read_text(encoding="utf-8")
        actions = re.findall(r"uses:\s*(\S+)", workflow)
        self.assertEqual(len(actions), 3)
        self.assertTrue(all(re.fullmatch(r"actions/[a-z-]+@[0-9a-f]{40}", action)
                            for action in actions))
        self.assertIn("permissions:\n  contents: read\n", workflow)
        self.assertEqual(workflow.count("fetch-depth: 0"), 2)
        self.assertEqual(workflow.count("persist-credentials: false"), 2)
        for command in ("python3 tools/check_secrets.py", "python tools/validate_public_tree.py",
                        "python tools/build_excluded_inventory.py --check",
                        "python -m unittest discover -s tests",
                        "python tools/buddhist_canon_pipeline/build_deploy_site.py --reader-jobs 2"):
            self.assertIn(command, workflow)
        for forbidden in ("pull_request_target", "contents: write", "git push", "deploy:"):
            self.assertNotIn(forbidden, workflow)
        self.assertNotRegex(workflow, r"\$\{\{[^}]*\bsecrets\b")

    @staticmethod
    def archive(binary=b"verified test executable", kind=tarfile.REGTYPE):
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode="w:gz") as archive:
            member = tarfile.TarInfo("gitleaks")
            member.type = kind
            member.size = len(binary) if kind == tarfile.REGTYPE else 0
            archive.addfile(member, io.BytesIO(binary) if member.size else None)
        return stream.getvalue()

    def test_scanner_archive_requires_exact_checksum_and_regular_binary(self):
        archive = self.archive()
        with patch.object(check_secrets, "ARCHIVE_SHA256", hashlib.sha256(archive).hexdigest()):
            self.assertEqual(check_secrets.verified_binary(archive), b"verified test executable")
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                check_secrets.verified_binary(archive + b"changed")
        linked = self.archive(kind=tarfile.SYMTYPE)
        with patch.object(check_secrets, "ARCHIVE_SHA256", hashlib.sha256(linked).hexdigest()):
            with self.assertRaisesRegex(ValueError, "one regular executable"):
                check_secrets.verified_binary(linked)

    def test_valid_cached_archive_needs_no_network_and_repairs_changed_executable(self):
        archive = self.archive()
        with tempfile.TemporaryDirectory() as temporary:
            cache = Path(temporary)
            (cache / "release.tar.gz").write_bytes(archive)
            (cache / "gitleaks").write_bytes(b"not the verified executable")
            with (patch.object(check_secrets, "ARCHIVE_SHA256", hashlib.sha256(archive).hexdigest()),
                  patch.object(check_secrets, "urlopen") as network):
                executable = check_secrets.ensure_scanner(cache)
            network.assert_not_called()
            self.assertEqual(executable.read_bytes(), b"verified test executable")
            self.assertEqual(executable.stat().st_mode & 0o777, 0o700)

    def test_bad_cached_archive_fails_without_download_or_execution(self):
        with tempfile.TemporaryDirectory() as temporary:
            cache = Path(temporary)
            (cache / "release.tar.gz").write_bytes(b"corrupted cache")
            with (patch.object(check_secrets, "urlopen") as network,
                  patch.object(check_secrets.subprocess, "run") as execute):
                with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                    check_secrets.ensure_scanner(cache)
            network.assert_not_called()
            execute.assert_not_called()

    def test_download_is_verified_before_it_is_cached_or_executed(self):
        archive = self.archive()
        with tempfile.TemporaryDirectory() as temporary:
            cache = Path(temporary)
            with (patch.object(check_secrets, "ARCHIVE_SHA256", hashlib.sha256(archive).hexdigest()),
                  patch.object(check_secrets, "urlopen") as network):
                network.return_value.__enter__.return_value.read.return_value = archive
                executable = check_secrets.ensure_scanner(cache)
            network.assert_called_once_with(check_secrets.ARCHIVE_URL, timeout=60)
            self.assertEqual(executable.read_bytes(), b"verified test executable")
            self.assertEqual((cache / "release.tar.gz").read_bytes(), archive)
        with tempfile.TemporaryDirectory() as temporary:
            cache = Path(temporary)
            with patch.object(check_secrets, "urlopen") as network:
                network.return_value.__enter__.return_value.read.return_value = b"untrusted download"
                with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                    check_secrets.ensure_scanner(cache)
            self.assertEqual(list(cache.iterdir()), [])

    def test_scanner_rejects_symlinks_and_unsupported_platforms(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "linked").symlink_to(root, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "symlinked scanner cache"):
                check_secrets.ensure_scanner(root / "linked")
        with patch.object(check_secrets.platform, "machine", return_value="aarch64"):
            with self.assertRaisesRegex(ValueError, "Linux x86-64"):
                check_secrets.ensure_scanner()

    def test_scan_covers_all_refs_redacts_output_and_propagates_failure(self):
        with (patch.object(check_secrets.subprocess, "run") as execute,
              patch.dict(os.environ, {"GITLEAKS_CONFIG": "unreviewed", "GITLEAKS_CONFIG_TOML": "bypass"})):
            execute.side_effect = [subprocess.CompletedProcess([], 0, stdout="false\n"),
                                   subprocess.CompletedProcess([], 1)]
            self.assertEqual(check_secrets.scan(ROOT, Path("/verified/gitleaks")), 1)
            arguments, options = execute.call_args
            self.assertIn("--log-opts=--all", arguments[0])
            self.assertIn("--redact=100", arguments[0])
            self.assertIn("--ignore-gitleaks-allow", arguments[0])
            self.assertNotIn("GITLEAKS_CONFIG", options["env"])
            self.assertNotIn("GITLEAKS_CONFIG_TOML", options["env"])
        with patch.object(check_secrets.subprocess, "run") as execute:
            execute.return_value = subprocess.CompletedProcess([], 0, stdout="true\n")
            with self.assertRaisesRegex(ValueError, "complete history"):
                check_secrets.scan(ROOT, Path("/verified/gitleaks"))
            self.assertEqual(execute.call_count, 1)

    @unittest.skipUnless(os.environ.get("GITLEAKS_INTEGRATION") == "1",
                         "explicit integration run uses the checksum-verified scanner")
    def test_real_pre_push_hook_accepts_clean_history_and_blocks_added_or_deleted_fake_secret(self):
        scanner = check_secrets.ensure_scanner()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = root / "source"
            remote = root / "remote.git"
            subprocess.run(["git", "init", "--bare", "--quiet", str(remote)], check=True)
            subprocess.run(["git", "init", "--quiet", str(repository)], check=True)

            def git(*arguments):
                return subprocess.run(["git", *arguments], cwd=repository,
                                      capture_output=True, text=True, check=True)

            git("config", "user.name", "Scanner regression fixture")
            git("config", "user.email", "scanner@example.invalid")
            for relative in ("tools/check_secrets.py", ".githooks/pre-push"):
                destination = repository / relative
                destination.parent.mkdir(exist_ok=True)
                shutil.copy2(ROOT / relative, destination)
            cache = repository / "build/security-tools" / f"gitleaks-{check_secrets.VERSION}"
            cache.mkdir(parents=True)
            shutil.copy2(scanner.parent / "release.tar.gz", cache / "release.tar.gz")
            git("config", "core.hooksPath", ".githooks")
            git("remote", "add", "fixture", str(remote))
            (repository / "README.md").write_text("Clean scanner fixture.\n", encoding="utf-8")
            git("add", "README.md")
            git("commit", "--quiet", "-m", "Clean fixture")
            git("push", "fixture", "HEAD:refs/heads/review")
            clean = git("rev-parse", "HEAD").stdout.strip()

            fake = "ghp_" + "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(36))
            credential = repository / "fake-credential.txt"
            credential.write_text("GITHUB_TOKEN=" + fake + "\n", encoding="utf-8")
            git("add", credential.name)
            git("commit", "--quiet", "-m", "Deliberately fake credential")
            for deleted in (False, True):
                if deleted:
                    git("rm", "--quiet", credential.name)
                    git("commit", "--quiet", "-m", "Deletion must not clear old findings")
                result = subprocess.run(["git", "push", "fixture", "HEAD:refs/heads/review"],
                                        cwd=repository, capture_output=True, text=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("leaks found", result.stdout + result.stderr)
                self.assertNotIn(fake, result.stdout + result.stderr)
                self.assertEqual(git("ls-remote", "fixture", "refs/heads/review").stdout.split()[0], clean)


if __name__ == "__main__":
    unittest.main()
