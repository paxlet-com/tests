"""Component and CLI E2E checks for Taskand shell integration.

Validates these shell pipeline boundaries:
1. Exact natural-language catalog aliases (nl-dsl-sh)
2. Deterministic compilation into verifiable scripts
3. Paxlet package structure and content digests
4. Subprocess execution and receipt content (Docker supplies OS isolation)
5. Digest mismatch rejection, workspace IDs, and build/run separation.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
import unittest


def resolve_taskand_root() -> Path:
    if "TASKAND_ROOT" in os.environ:
        return Path(os.environ["TASKAND_ROOT"]).resolve()
    current = Path(__file__).resolve()
    for parent in current.parents:
        candidate = parent / "taskand"
        if candidate.is_dir() and (candidate / "bin/taskand").is_file():
            return candidate
    return Path("/home/tom/github/paxlet-com/taskand")


TASKAND_ROOT = resolve_taskand_root()
SHELL_VENV_PYTHON = TASKAND_ROOT / ".subactor/cache/shell-venv/bin/python"


class TestTaskandPaxletAutonomyE2E(unittest.TestCase):
    """End-to-End autonomy validation suite."""

    @classmethod
    def setUpClass(cls):
        app_dir = str(TASKAND_ROOT)
        if app_dir not in sys.path:
            sys.path.insert(0, app_dir)

    def test_01_nl_planning_compilation_and_paxlet_export(self):
        """NL prompt -> Catalog reuse / Plan -> Paxlet package export."""
        from nl_dsl_sh import Catalog, Engine, Plan
        from nl_dsl_sh.interop import export_paxlet
        from paxlet.manifest import load_manifest, package_digest, validate_manifest

        with tempfile.TemporaryDirectory(prefix="paxlet-e2e-catalog-") as tmpdir:
            tmp = Path(tmpdir)
            source = tmp / "memcheck.py"
            source.write_text("import sys\nprint('MEMORY_STATUS_OK')\nsys.exit(0)\n", encoding="utf-8")

            catalog = Catalog()
            catalog.import_script(
                source,
                script_id="urn:nl-dsl-sh:taskand:e2e-mem",
                description="Memory check",
                language="python",
                aliases=["sprawdź stan pamięci"],
            )

            engine = Engine(catalog=catalog)
            plan = engine.plan("sprawdź stan pamięci", language="python", reuse_only=True)
            self.assertIsInstance(plan, Plan)
            self.assertEqual(len(plan.steps), 1)

            artifact = engine.compile(plan, format="python")
            self.assertIn("Standalone nl-dsl-sh bundle", artifact.script)
            self.assertEqual(artifact.report["steps"], 1)

            pkg_dir = tmp / "memory-checker"
            exported_path = export_paxlet(
                artifact,
                pkg_dir,
                urn="urn:paxlet:test:memory-checker",
                permissions={},
            )
            self.assertTrue(exported_path.is_dir())

            manifest_path, manifest = load_manifest(exported_path)
            validation = validate_manifest(manifest_path.parent, manifest)
            self.assertTrue(validation.ok, f"Validation failed: {validation.errors}")

            digest = package_digest(manifest_path.parent, manifest)
            self.assertTrue(digest.startswith("sha256:"))

    def test_02_paxlet_isolated_execution_and_receipt(self):
        """Verify receipt fields and input/output hashes; receipts are not signed."""
        from paxlet.runtime import run_action
        from app.shell_workflow import export_package

        plan = {
            "schema_version": "0.1",
            "name": "autonomy-e2e-run",
            "steps": [
                {
                    "id": "step_compute",
                    "kind": "generate",
                    "language": "python",
                    "code": "result = sum(range(1, 101))\nprint(f'SUM_1_TO_100={result}')\n",
                }
            ],
        }

        with tempfile.TemporaryDirectory(prefix="paxlet-e2e-run-") as tmpdir:
            pkg_dir = Path(tmpdir) / "compute-task"
            exported = export_package(
                plan,
                pkg_dir,
                urn="urn:paxlet:test:compute",
                permissions={},
            )
            digest = exported["digest"]
            self.assertTrue(digest.startswith("sha256:"))

            output, receipt, receipt_path = run_action(pkg_dir, "run", {"stdin": ""})
            self.assertEqual(output["exit_code"], 0)
            self.assertIn("SUM_1_TO_100=5050", output["stdout"])

            self.assertIsNotNone(receipt)
            self.assertEqual(receipt["action"], "run")
            self.assertEqual(receipt["package_digest"], digest)
            self.assertEqual(receipt["exit_code"], 0)
            self.assertTrue(Path(receipt_path).is_file())
            from paxlet.receipt import value_digest
            self.assertEqual(receipt["input_digest"], value_digest({"stdin": ""}))
            self.assertEqual(receipt["output_digest"], value_digest(output))
            self.assertEqual(json.loads(Path(receipt_path).read_text()), receipt)

    def test_03_fail_closed_tampering_protection(self):
        """Tampering with packaged files must block execution via digest verification."""
        from app.shell_workflow import export_package, run_package

        plan = {
            "schema_version": "0.1",
            "name": "tamper-test",
            "steps": [
                {
                    "id": "step1",
                    "kind": "generate",
                    "language": "python",
                    "code": "print('SAFE_PAYLOAD')\n",
                }
            ],
        }

        with tempfile.TemporaryDirectory(prefix="paxlet-tamper-") as tmpdir:
            pkg_dir = Path(tmpdir) / "tamper-task"
            exported = export_package(
                plan,
                pkg_dir,
                urn="urn:paxlet:test:tamper",
                permissions={},
            )
            original_digest = exported["digest"]

            # 1. Running with altered expected digest must fail closed
            with self.assertRaises(ValueError) as ctx:
                run_package(pkg_dir, expected_digest="sha256:0000000000000000000000000000000000000000000000000000000000000000")
            self.assertIn("digest mismatch", str(ctx.exception).lower())

            # 2. Tampering with code on disk without updating manifest must fail verification
            code_file = pkg_dir / "task.py"
            self.assertTrue(code_file.is_file(), "Exporter changed: update the tampering fixture")
            code_file.write_text("print('MALICIOUS_PAYLOAD')\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                run_package(pkg_dir, expected_digest=original_digest)
            self.assertFalse((pkg_dir / ".paxlet/receipts").exists())

    def test_04_cli_routing_and_workspace_confinement(self):
        """Universal Taskand CLI 'taskand shell' subcommands execution."""
        taskand_bin = TASKAND_ROOT / "bin/taskand"
        if not taskand_bin.is_file():
            self.fail("taskand bin not found; set TASKAND_ROOT")

        python_bin = os.environ.get("TASKAND_SHELL_PYTHON", sys.executable)

        with tempfile.TemporaryDirectory(prefix="taskand-cli-test-") as tmpdir:
            # CLI audit state is rooted beside its executable, with no environment
            # override. Copy only source inputs so tests cannot touch host .env/log.
            isolated = Path(tmpdir) / "taskand"
            isolated.mkdir()
            for name in ("bin", "operations", "generated", "app", "gateway"):
                shutil.copytree(TASKAND_ROOT / name, isolated / name,
                                ignore=shutil.ignore_patterns(".*", "__pycache__", "*.pyc"))
            shutil.copyfile(TASKAND_ROOT / "genome.yaml", isolated / "genome.yaml")
            taskand_bin = isolated / "bin/taskand"
            env = {
                "PATH": os.environ["PATH"],
                "HOME": tmpdir,
                "PYTHONDONTWRITEBYTECODE": "1",
                "TASKAND_GATEWAY": "http://127.0.0.1:9",
                "TASKAND_SHELL_WORKSPACE": tmpdir,
                "TASKAND_SHELL_PYTHON": python_bin,
            }

            export_payload = json.dumps({
                "id": "cli-test",
                "plan": {
                    "schema_version": "0.1",
                    "name": "cli-demo",
                    "steps": [{"id": "s1", "kind": "generate", "language": "python", "code": "print('CLI_E2E_OK')\n"}],
                },
                "urn": "urn:paxlet:cli:test",
                "permissions": {},
            })

            # Export
            res = subprocess.run(
                ["node", str(taskand_bin), "shell", "export", export_payload, "--json"],
                capture_output=True,
                timeout=20,
                text=True,
                env=env,
            )
            self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
            data = json.loads(res.stdout)
            self.assertTrue(data["ok"])
            digest = data["result"]["digest"]

            # Verify
            res = subprocess.run(
                ["node", str(taskand_bin), "shell", "verify", json.dumps({"id": "cli-test"}), "--json"],
                capture_output=True,
                timeout=20,
                text=True,
                env=env,
            )
            self.assertEqual(res.returncode, 0)
            verify_data = json.loads(res.stdout)
            self.assertEqual(verify_data["result"]["digest"], digest)

            # Run with expected digest
            res = subprocess.run(
                ["node", str(taskand_bin), "shell", "run", json.dumps({"id": "cli-test", "expected_digest": digest}), "--json"],
                capture_output=True,
                timeout=20,
                text=True,
                env=env,
            )
            self.assertEqual(res.returncode, 0)
            run_data = json.loads(res.stdout)
            self.assertIn("CLI_E2E_OK", run_data["result"]["output"]["stdout"])

    def test_nonzero_step_stops_dependencies_and_records_failure(self):
        from app.shell_workflow import export_package, run_package
        from paxlet.errors import RuntimeError as PaxletRuntimeError
        with tempfile.TemporaryDirectory() as tmp:
            package = Path(tmp) / "pkg"
            plan = {"steps": [
                {"id": "fail", "kind": "generate", "language": "python", "code": "raise SystemExit(7)\n"},
                {"id": "after", "kind": "generate", "language": "python", "needs": ["fail"],
                 "code": "from pathlib import Path\nPath('SHOULD_NOT_EXIST').write_text('ran')\n"},
            ]}
            exported = export_package(plan, package, urn="urn:paxlet:test:failure", permissions={})
            with self.assertRaises(PaxletRuntimeError):
                run_package(package, expected_digest=exported["digest"], timeout=5)
            self.assertFalse((package / "SHOULD_NOT_EXIST").exists())
            receipts = list((package / ".paxlet/receipts").glob("*.json"))
            self.assertEqual(len(receipts), 1)
            receipt = json.loads(receipts[0].read_text())
            self.assertEqual(receipt["exit_code"], 7)
            self.assertIsNone(receipt["output_digest"])

    def test_workspace_confinement(self):
        from app.shell_workflow import process_request
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"TASKAND_SHELL_WORKSPACE": tmp}):
            for identifier in ("../escape", "/tmp/escape", "a/b", "", "a" * 65):
                with self.subTest(identifier=identifier), self.assertRaises(ValueError):
                    process_request("verify", {"id": identifier})
            (Path(tmp) / "packages").symlink_to(Path(tmp), target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "symlinks"):
                process_request("verify", {"id": "escape"})

    def test_05_mcp_process_uri_separation(self):
        """Separate shell-build and shell-run process runners enforce least privilege."""
        build_bin = TASKAND_ROOT / "generated/mcp/shell-build/taskand.dev/v1/bin.mjs"
        run_bin = TASKAND_ROOT / "generated/mcp/shell-run/taskand.dev/v1/bin.mjs"

        if not (build_bin.is_file() and run_bin.is_file()):
            self.fail("MCP process runners not generated")

        # shell-build must reject 'run' operation
        res = subprocess.run(
            ["node", str(build_bin)],
            input=json.dumps({"operation": "run", "id": "any"}),
            capture_output=True,
            timeout=20,
            text=True,
        )
        self.assertEqual(res.returncode, 0)
        data = json.loads(res.stdout)
        self.assertFalse(data["ok"])
        self.assertIn("denied", data.get("error", "").lower())

        # shell-run must reject 'plan' or 'export' operation
        res = subprocess.run(
            ["node", str(run_bin)],
            input=json.dumps({"operation": "export", "id": "any"}),
            capture_output=True,
            timeout=20,
            text=True,
        )
        self.assertEqual(res.returncode, 0)
        data = json.loads(res.stdout)
        self.assertFalse(data["ok"])


if __name__ == "__main__":
    unittest.main()
