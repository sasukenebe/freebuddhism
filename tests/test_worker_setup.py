# SPDX-License-Identifier: 0BSD
import json
from pathlib import Path
import shlex
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import setup_worker as worker


class WorkerSetupTests(unittest.TestCase):
    def test_only_named_hosts_exact_commits_and_explicit_paths_are_accepted(self):
        good = ("worker-alias", "/srv/build/freebuddhism2", "a" * 40)
        worker.validate_target(*good)
        for index, value in ((0, "-oOption"), (0, "192.0.2.1"), (0, "host;command"),
                             (1, "/"), (1, "relative"), (1, "/srv/../other"),
                             (2, "main"), (2, "abcdef")):
            args = list(good)
            args[index] = value
            with self.subTest(args=args), self.assertRaises(ValueError): worker.validate_target(*args)

    def test_transport_stages_only_setup_code_and_uses_pinned_host_checks_without_agent(self):
        calls = []
        def command(args, **kwargs):
            calls.append(args)
            return subprocess.CompletedProcess(args, 0, "/tmp/freebuddhism-bootstrap.abcdefgh\n", "")
        with patch.object(worker.shutil, "which", return_value="/synthetic/tool"), \
                patch.object(worker.subprocess, "run", side_effect=command), \
                patch.object(worker.sys.stdin, "isatty", return_value=True):
            worker.setup("worker-alias", "/srv/build/reader's copy", "a" * 40, install=True)
        self.assertEqual(len(calls), 3)
        for args in calls:
            self.assertIn("StrictHostKeyChecking=yes", args)
            self.assertIn("ForwardAgent=no", args)
        copied = calls[1]
        self.assertEqual([Path(p).name for p in copied if p.endswith((".py", ".txt"))],
                         ["bootstrap.py", "requirements-system.txt"])
        remote = shlex.split(calls[2][-1])
        self.assertEqual(remote[4:], ["/srv/build/reader's copy", "a" * 40,
                         "/tmp/freebuddhism-bootstrap.abcdefgh", worker.SOURCE_URL, "yes"])
        self.assertIn("-t", calls[2])

    def test_unexpected_staging_path_and_noninteractive_sudo_fail_before_setup(self):
        with patch.object(worker.sys.stdin, "isatty", return_value=False), \
                patch.object(worker.subprocess, "run") as run:
            with self.assertRaisesRegex(ValueError, "terminal"):
                worker.setup("worker-alias", "/srv/build/freebuddhism2", "a" * 40, install=True)
            run.assert_not_called()
        with patch.object(worker.shutil, "which", return_value="/synthetic/tool"), \
                patch.object(worker.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "/unexpected\n")) as run:
            with self.assertRaisesRegex(ValueError, "staging"):
                worker.setup("worker-alias", "/srv/build/freebuddhism2", "a" * 40)
            self.assertEqual(run.call_count, 1)

    def test_remote_setup_reuses_only_matching_clean_checkout_and_preserves_other_work(self):
        with TemporaryDirectory() as directory:
            base = Path(directory)
            repo = base / "repo"
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            (repo / "requirements.txt").write_text("synthetic==1\n")
            subprocess.run(["git", "add", "requirements.txt"], cwd=repo, check=True)
            subprocess.run(["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                            "commit", "-qm", "Synthetic setup fixture"], cwd=repo, check=True)
            subprocess.run(["git", "remote", "add", "origin", worker.SOURCE_URL], cwd=repo, check=True)
            revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
            payload = base / "payload"
            payload.mkdir()
            (payload / "bootstrap.py").write_text("import sys; print('BOOTSTRAP_CALLED', sys.argv[1:])\n")
            def run(path=repo, rev=revision):
                return subprocess.run(["sh", "-c", worker.REMOTE_SETUP, "worker-setup", str(path),
                                       rev, str(payload), worker.SOURCE_URL, "no"], capture_output=True, text=True)
            self.assertIn("BOOTSTRAP_CALLED", run().stdout)
            dirty = repo / "user-work.txt"
            dirty.write_text("User changes")
            self.assertNotEqual(run().returncode, 0)
            self.assertEqual(dirty.read_text(), "User changes")
            dirty.unlink()
            self.assertNotEqual(run(rev="b" * 40).returncode, 0)
            link = base / "linked"
            link.symlink_to(repo, target_is_directory=True)
            self.assertNotEqual(run(path=link).returncode, 0)
            empty = base / "empty"
            empty.mkdir()
            self.assertNotEqual(run(path=empty).returncode, 0)
            subprocess.run(["git", "remote", "set-url", "origin", "https://example.invalid/different.git"], cwd=repo, check=True)
            self.assertNotEqual(run().returncode, 0)
            self.assertEqual(subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip(), revision)


if __name__ == "__main__":
    unittest.main()
