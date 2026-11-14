# SPDX-License-Identifier: 0BSD
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import bootstrap as boot


class BootstrapTests(unittest.TestCase):
    def files(self, root):
        (root / "requirements.txt").write_text("example-package==1.2.3\n")
        packages = root / "requirements-system.txt"
        packages.write_text("python3-venv\npoppler-utils\n")
        return packages

    def owned(self, root):
        env = root / ".venv"
        env.mkdir()
        (env / ".freebuddhism-bootstrap.json").write_text(json.dumps(boot.MARKER))
        return env

    def test_requirements_are_exact_distinct_pins_and_system_names_not_commands(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "requirements.txt"
            for value in ("example>=1", "https://example.org/pkg.whl", "", "Example_A==1\nexample-a==2"):
                path.write_text(value)
                with self.subTest(value=value), self.assertRaises(boot.SetupError):
                    boot.python_requirements(path)
            path.write_text("# comment\nExample_A==1.2.3\n")
            self.assertEqual(boot.python_requirements(path), {"example-a": "1.2.3"})
            for value in ("--option", "pkg; command", "pkg\npkg", ""):
                path.write_text(value)
                with self.subTest(value=value), self.assertRaises(boot.SetupError):
                    boot.system_requirements(path)

    def test_foreign_environment_or_symlink_is_rejected_before_system_changes(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            packages = self.files(root)
            env = root / ".venv"
            env.mkdir()
            original = env / "keep.txt"
            original.write_text("Existing user environment")
            with patch.object(boot, "install_system") as installer:
                with self.assertRaisesRegex(boot.SetupError, "left unchanged"):
                    boot.bootstrap(root, packages, install=True)
                installer.assert_not_called()
            self.assertEqual(original.read_text(), "Existing user environment")
            link_root = root / "linked"
            link_root.mkdir()
            (link_root / ".venv").symlink_to(env, target_is_directory=True)
            with self.assertRaisesRegex(boot.SetupError, "linked"):
                boot.checked_environment(link_root)

    def test_check_and_missing_system_tools_never_create_an_environment(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            packages = self.files(root)
            with patch.object(boot, "system_problems", return_value=["Missing native tool: mutool"]), \
                    patch.object(boot, "run") as run:
                for check in (False, True):
                    with self.subTest(check=check), self.assertRaisesRegex(boot.SetupError, "mutool"):
                        boot.bootstrap(root, packages, check=check)
                run.assert_not_called()
            self.assertFalse((root / ".venv").exists())

    def test_managed_environment_creation_resumes_without_deleting_or_recreating(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            env = root / ".venv"
            def create(command):
                self.assertEqual(command, [sys.executable, "-m", "venv", str(env)])
                python = boot.environment_python(env)
                python.parent.mkdir(parents=True)
                python.write_text("synthetic interpreter")
            with patch.object(boot, "run", side_effect=create) as run:
                boot.create_environment(env)
                boot.create_environment(boot.checked_environment(root))
                self.assertEqual(run.call_count, 1)
            self.assertEqual(json.loads((env / ".freebuddhism-bootstrap.json").read_text()), boot.MARKER)

    def test_install_uses_only_pinned_requirements_and_checks_dependency_consistency(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            packages = self.files(root)
            python = root / ".venv/bin/python"
            with patch.object(boot, "system_problems", return_value=[]), \
                    patch.object(boot, "create_environment", return_value=python), \
                    patch.object(boot, "environment_problems", return_value=[]), \
                    patch.object(boot, "ensure_pip"), \
                    patch.object(boot, "run") as run:
                report = boot.bootstrap(root, packages)
            self.assertEqual(report["status"], "READY")
            self.assertEqual(run.call_args_list[0].args[0], [str(python), "-m", "pip", "--disable-pip-version-check",
                "install", "--only-binary=:all:", "-r", str(root / "requirements.txt")])
            self.assertEqual(run.call_args_list[1].args[0], [str(python), "-m", "pip", "check"])

    def test_check_does_not_install_and_propagates_package_mismatches(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            packages = self.files(root)
            self.owned(root)
            with patch.object(boot, "system_problems", return_value=[]), \
                    patch.object(boot, "environment_problems", return_value=["Expected example-package==1.2.3"]), \
                    patch.object(boot, "create_environment") as create, patch.object(boot, "run") as run:
                with self.assertRaisesRegex(boot.SetupError, "Expected example-package"):
                    boot.bootstrap(root, packages, check=True)
                create.assert_not_called()
                run.assert_not_called()

    def test_package_inventory_rejects_wrong_python_pins_and_system_site_packages(self):
        with TemporaryDirectory() as directory:
            env = self.owned(Path(directory))
            python = boot.environment_python(env)
            python.parent.mkdir(parents=True)
            python.write_text("synthetic interpreter")
            (env / "pyvenv.cfg").write_text("include-system-site-packages = true\n")
            result = subprocess.CompletedProcess([], 0, json.dumps({"isolated": True, "python": [3, 11],
                                                                  "packages": {"example": "1"}}))
            with patch.object(boot.subprocess, "run", return_value=result):
                problems = boot.environment_problems(python, {"example": "2"})
            self.assertEqual(len(problems), 3)

    def test_nonisolated_managed_python_cannot_install_system_or_python_packages(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            packages = self.files(root)
            env = self.owned(root)
            python = boot.environment_python(env)
            python.parent.mkdir(parents=True)
            python.write_text("synthetic nonisolated interpreter")
            with patch.object(boot, "environment_problems", return_value=["Virtual environment is not isolated"]), \
                    patch.object(boot, "install_system") as install, patch.object(boot, "run") as run:
                with self.assertRaisesRegex(boot.SetupError, "not isolated"):
                    boot.bootstrap(root, packages, install=True)
                install.assert_not_called()
                run.assert_not_called()

    def test_missing_pip_in_a_managed_environment_is_repaired_without_network(self):
        with patch.object(boot.subprocess, "run", return_value=subprocess.CompletedProcess([], 1)), \
                patch.object(boot, "run") as run:
            boot.ensure_pip(Path("managed/python"))
            run.assert_called_once_with(["managed/python", "-m", "ensurepip", "--upgrade"])

    def test_native_checks_reject_font_fallback_and_broken_executables(self):
        def version(command, **kwargs):
            output = "Liberation Sans|Regular" if command[0] == "fc-match" else "version"
            return subprocess.CompletedProcess(command, 1 if command[0] == "mutool" else 0, output, "")
        with patch.object(boot.shutil, "which", return_value="/synthetic/tool"), \
                patch.object(boot.subprocess, "run", side_effect=version):
            problems = boot.system_problems()
        self.assertEqual(len(problems), 3)
        self.assertTrue(any("fallback" in p for p in problems))

    def test_system_install_is_explicit_platform_scoped_and_uses_declared_packages(self):
        with patch.object(boot.sys, "platform", "linux"), \
                patch.object(boot.platform, "freedesktop_os_release", return_value={"ID": "ubuntu"}), \
                patch.object(boot.os, "geteuid", return_value=1000, create=True), \
                patch.object(boot.shutil, "which", return_value="/synthetic/tool"), patch.object(boot, "run") as run:
            boot.install_system(["python3-venv", "mupdf-tools"])
            self.assertEqual(run.call_args_list[0].args[0], ["sudo", "apt-get", "update"])
            self.assertEqual(run.call_args_list[1].args[0], ["sudo", "apt-get", "install", "--no-install-recommends",
                                                          "-y", "python3-venv", "mupdf-tools"])
        with patch.object(boot.sys, "platform", "darwin"), patch.object(boot, "run") as run:
            with self.assertRaises(boot.SetupError): boot.install_system(["package"])
            run.assert_not_called()

    def test_cli_failure_is_not_reported_as_success(self):
        with patch.object(boot, "bootstrap", side_effect=subprocess.CalledProcessError(1, ["pip"])):
            self.assertEqual(boot.main(["--check"]), 1)


if __name__ == "__main__":
    unittest.main()
