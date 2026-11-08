import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import validate_public_tree as validator  # noqa: E402


class TrackedFileTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.git("init", "--quiet")
        (self.root / ".gitignore").write_text("/build/\n/.venv/\n__pycache__/\n", encoding="utf-8")

    def git(self, *arguments):
        return subprocess.run(["git", *arguments], cwd=self.root,
                              check=True, capture_output=True, text=True)

    def track(self, name):
        path = self.root / name
        path.parent.mkdir(exist_ok=True, parents=True)
        path.write_text("Non-sensitive regression fixture.\n", encoding="utf-8")
        self.git("add", "--force", "--", name)

    def test_force_added_excluded_paths_fail_even_if_allowlisted(self):
        for name in ("build/forced.txt", ".venv/forced.txt", "tools/__pycache__/forced.txt"):
            with self.subTest(name=name):
                self.track(name)
                with self.assertRaisesRegex(ValueError, "excluded or unsafe path"):
                    validator.validate_tracked_files({name}, self.root)
                self.git("rm", "--cached", "--force", "--", name)

    def test_unlisted_tracked_file_is_rejected(self):
        self.track("unlisted.txt")
        with self.assertRaisesRegex(ValueError, "no exact allowlist entry"):
            validator.validate_tracked_files(set(), self.root)

    def test_approved_paths_with_tabs_and_newlines_are_not_split(self):
        names = {"docs/ordinary.txt", "docs/tab\tname.txt", "docs/newline\nname.txt"}
        for name in names:
            self.track(name)
        self.assertEqual(validator.validate_tracked_files(names, self.root), 3)

    def test_missing_working_file_remains_in_the_tracked_check(self):
        self.track("deleted.txt")
        (self.root / "deleted.txt").unlink()
        with self.assertRaisesRegex(ValueError, "no exact allowlist entry"):
            validator.validate_tracked_files(set(), self.root)

    def test_tracked_symlinks_and_submodule_entries_are_rejected(self):
        (self.root / "linked").symlink_to("unrelated")
        self.git("add", "linked")
        with self.assertRaisesRegex(ValueError, "regular with no merge conflicts"):
            validator.validate_tracked_files({"linked"}, self.root)
        self.git("rm", "--cached", "--force", "linked")
        # A gitlink can hide a whole separate tree; it is not an approved regular file.
        self.git("update-index", "--add", "--cacheinfo", "160000," + "1" * 40 + ",nested")
        with self.assertRaisesRegex(ValueError, "regular with no merge conflicts"):
            validator.validate_tracked_files({"nested"}, self.root)

    def test_conflicted_index_entries_are_rejected(self):
        object_id = self.git("hash-object", "-w", ".gitignore").stdout.strip()
        subprocess.run(["git", "update-index", "--index-info"], cwd=self.root, check=True,
                       input=f"100644 {object_id} 1\tconflicted\n", text=True)
        with self.assertRaisesRegex(ValueError, "regular with no merge conflicts"):
            validator.validate_tracked_files({"conflicted"}, self.root)

    def test_git_failure_or_wrong_repository_root_cannot_skip_the_check(self):
        nested = self.root / "nested"
        nested.mkdir()
        with self.assertRaisesRegex(ValueError, "exact Git repository root"):
            validator.validate_tracked_files(set(), nested)
        with tempfile.TemporaryDirectory() as outside:
            with self.assertRaisesRegex(ValueError, "requires Git"):
                validator.validate_tracked_files(set(), Path(outside))
        with patch.object(validator.subprocess, "run", side_effect=FileNotFoundError("git")):
            with self.assertRaisesRegex(ValueError, "requires Git"):
                validator.validate_tracked_files(set(), self.root)

    def test_check_and_checksum_refresh_both_reject_the_blind_spot(self):
        self.track("build/forced.txt")
        manifest = self.root / "allowlist.json"
        manifest.write_text(json.dumps({
            "scope": "Exact path, content hash, license scope, and rights basis are required; new files are denied by default.",
            "files": [{"path": "build/forced.txt", "sha256": "0" * 64,
                       "license_scope": "0BSD", "rights_basis": validator.RIGHTS_BASIS_BY_SCOPE["0BSD"]}],
        }), encoding="utf-8")
        original = manifest.read_bytes()
        with patch.object(validator, "ROOT", self.root), patch.object(validator, "ALLOWLIST", manifest):
            with self.assertRaisesRegex(ValueError, "excluded or unsafe path"):
                validator.check()
            with self.assertRaisesRegex(ValueError, "excluded or unsafe path"):
                validator.write_allowlist({"build/forced.txt"})
        self.assertEqual(manifest.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
