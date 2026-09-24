#!/usr/bin/env python3
"""End-to-end validation of NL-to-Paxlet pipeline across a 3-node Taskand cluster mesh."""

from __future__ import annotations

import json
import subprocess
import unittest


def run_docker_exec(container: str, cmd: str) -> tuple[int, str, str]:
    """Execute a bash command inside a running Docker container."""
    res = subprocess.run(
        ["docker", "exec", container, "bash", "-c", cmd],
        capture_output=True,
        text=True,
    )
    return res.returncode, res.stdout, res.stderr


class TestNLPaxletClusterPipeline(unittest.TestCase):
    """Validates complete lifecycle: NL Plan -> Paxlet bundle -> Registry -> Mesh pull -> 3-node execution."""

    CLUSTER_TOKEN = "test-cluster-auth-token"
    PROC_URI = "proc://taskand.dev/cluster/distributed-audit/v1"
    PAXLET_URN = "urn:paxlet:cluster-distributed-audit"

    def test_01_nl_plan_compilation_and_paxlet_packaging_on_node1(self):
        """Node 1 compiles an NL-derived plan into a cryptographically verified Paxlet package."""
        plan_dict = {
            "schema_version": "0.1",
            "name": "cluster-distributed-audit",
            "description": "Multi-node cluster autonomous audit and compute task",
            "steps": [
                {
                    "id": "step1",
                    "kind": "generate",
                    "language": "python",
                    "code": (
                        "import os, json, platform\n"
                        "out = {'node': platform.node(), 'arch': platform.machine(), 'status': 'HEALTHY', 'audit_id': 42}\n"
                        "print('PAYLOAD_AUDIT:' + json.dumps(out))\n"
                    ),
                    "description": "Collect node identity and system audit data",
                }
            ],
        }
        plan_json = json.dumps(plan_dict)

        cmd = f"""cat << 'EOF' > /tmp/plan.json
{plan_json}
EOF
python3 -c '
import json, sys, shutil
from pathlib import Path
for p in ["/opt/paxlet", "/opt/nl-dsl-sh/src", "/opt/taskand"]:
    if p not in sys.path:
        sys.path.insert(0, p)
from app.shell_workflow import export_package, verify_package

plan = json.loads(Path("/tmp/plan.json").read_text())
pkg_dir = Path("/opt/taskand/log/shell/packages/cluster-distributed-audit")
if pkg_dir.exists():
    shutil.rmtree(pkg_dir)
exported = export_package(plan, pkg_dir, urn="{self.PAXLET_URN}", permissions={{"fs": ["read"]}})
verified = verify_package(pkg_dir)

result = {{
    "urn": exported["urn"],
    "digest": exported["digest"],
    "verified_digest": verified["digest"],
    "manifest_ok": exported["digest"] == verified["digest"]
}}
print(json.dumps(result))
'
"""
        code, out, err = run_docker_exec("taskand-node1", cmd)
        self.assertEqual(code, 0, f"Paxlet packaging failed on node1: {err}\n{out}")

        lines = [line.strip() for line in out.splitlines() if line.strip().startswith("{")]
        self.assertTrue(lines, f"No JSON output from packaging: {out}")
        data = json.loads(lines[-1])
        self.assertEqual(data["urn"], self.PAXLET_URN)
        self.assertTrue(data["digest"].startswith("sha256:"))
        self.assertTrue(data["manifest_ok"])

    def test_02_wrap_paxlet_into_cluster_procedure_and_catalog_admission(self):
        """Node 1 embeds the Paxlet execution into a cluster procedure and registers it."""
        setup_proc_cmd = f"""
rm -rf /opt/taskand/generated/cluster/distributed-audit
curl -s -X POST http://127.0.0.1:8077/api/registry \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer {self.CLUSTER_TOKEN}" \\
  -d '{{"action": "scan", "adopt": true}}' > /dev/null

mkdir -p /opt/taskand/generated/cluster/distributed-audit/taskand.dev/v1
cat << "EOF" > /opt/taskand/generated/cluster/distributed-audit/taskand.dev/v1/proc.yaml
uri: {self.PROC_URI}
desc: Multi-node distributed audit executed via Paxlet runtime
kind: task
origin: builtin
env: [TASKAND_NODE, PYTHONPATH]
EOF

cat << "EOF" > /opt/taskand/generated/cluster/distributed-audit/taskand.dev/v1/bin.mjs
#!/usr/bin/env node
import {{ spawnSync }} from "node:child_process";
import {{ writeFileSync }} from "node:fs";

const pythonScript = `
import os, sys, json
for p in ["/opt/paxlet", "/opt/nl-dsl-sh/src", "/opt/taskand"]:
    if p not in sys.path:
        sys.path.insert(0, p)
from app.shell_workflow import run_package, verify_package
from pathlib import Path

pkg_dir = Path("/opt/taskand/log/shell/packages/cluster-distributed-audit")
if not pkg_dir.exists():
    from app.shell_workflow import export_package
    plan = {{
        "schema_version": "0.1",
        "name": "cluster-distributed-audit",
        "description": "Multi-node cluster autonomous audit and compute task",
        "steps": [
            {{
                "id": "step1",
                "kind": "generate",
                "language": "python",
                "code": (
                    "import os, json, platform\\\\n"
                    "out = {{'node': platform.node(), 'arch': platform.machine(), 'status': 'HEALTHY', 'audit_id': 42}}\\\\n"
                    "print('PAYLOAD_AUDIT:' + json.dumps(out))\\\\n"
                ),
                "description": "Collect node identity and system audit data"
            }}
        ]
    }}
    export_package(plan, pkg_dir, urn="{self.PAXLET_URN}", permissions={{"fs": ["read"]}})

verified = verify_package(pkg_dir)
run_res = run_package(pkg_dir, expected_digest=verified["digest"])
payload_line = [l for l in run_res["output"]["stdout"].splitlines() if "PAYLOAD_AUDIT:" in l][0]
audit_data = json.loads(payload_line.split("PAYLOAD_AUDIT:")[1])

result = {{
    "ok": True,
    "node": audit_data["node"],
    "status": audit_data["status"],
    "audit_id": audit_data["audit_id"],
    "receipt_success": run_res["receipt"]["exit_code"] == 0,
    "paxlet_digest": verified["digest"]
}}
print(json.dumps(result))
`;

const res = spawnSync("python3", ["-c", pythonScript], {{
    encoding: "utf8",
    env: process.env
}});

if (res.status === 0 && res.stdout) {{
    const lines = res.stdout.trim().split("\\n");
    const jsonLine = lines.filter(l => l.startsWith("{{")).pop();
    writeFileSync(1, jsonLine + "\\n");
    process.exit(0);
}} else {{
    writeFileSync(2, (res.stderr || "execution failed") + "\\n");
    process.exit(1);
}}
EOF
chmod +x /opt/taskand/generated/cluster/distributed-audit/taskand.dev/v1/bin.mjs

curl -s -X POST http://127.0.0.1:8077/api/registry \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer {self.CLUSTER_TOKEN}" \\
  -d '{{"action": "scan", "adopt": true}}'
"""
        code, out, err = run_docker_exec("taskand-node1", setup_proc_cmd)
        self.assertEqual(code, 0, f"Procedure creation failed on node1: {err}\n{out}")

        # Verify exposed in node1 catalog (key: processes)
        code, out, _ = run_docker_exec(
            "taskand-node1",
            "curl -s http://127.0.0.1:8077/.well-known/catalog.json",
        )
        self.assertEqual(code, 0)
        catalog = json.loads(out)
        uris = [item.get("uri") for item in catalog.get("processes", [])]
        self.assertIn(self.PROC_URI, uris, f"Procedure {self.PROC_URI} not found in catalog: {uris}")

    def test_03_autonomous_peer_discovery_and_mesh_replication_to_node2_and_node3(self):
        """Node 2 and Node 3 discover and replicate the new package via cluster monitor."""
        # 1. Connect node2 and node3 to node1
        run_docker_exec("taskand-node2", "node /opt/taskand/bin/taskand peer add http://taskand-node1:8077")
        run_docker_exec("taskand-node3", "node /opt/taskand/bin/taskand peer add http://taskand-node1:8077")

        # 2. Trigger autonomous monitor pull on node2
        code, out, err = run_docker_exec(
            "taskand-node2",
            f'node /opt/taskand/bin/taskand --json proc proc://taskand.dev/cluster/monitor/v1 \'{{"pull":true,"token":"{self.CLUSTER_TOKEN}"}}\'',
        )
        self.assertEqual(code, 0, f"Monitor pull failed on node2: {err}")
        res2 = json.loads(out)
        self.assertTrue(res2.get("ok"))

        # 3. Trigger autonomous monitor pull on node3
        code, out, err = run_docker_exec(
            "taskand-node3",
            f'node /opt/taskand/bin/taskand --json proc proc://taskand.dev/cluster/monitor/v1 \'{{"pull":true,"token":"{self.CLUSTER_TOKEN}"}}\'',
        )
        self.assertEqual(code, 0, f"Monitor pull failed on node3: {err}")
        res3 = json.loads(out)
        self.assertTrue(res3.get("ok"))

        # 4. Verify procedure file exists on both target nodes
        for target in ["taskand-node2", "taskand-node3"]:
            code, out, _ = run_docker_exec(
                target,
                "test -f /opt/taskand/generated/cluster/distributed-audit/taskand.dev/v1/bin.mjs && echo EXISTS",
            )
            self.assertEqual(out.strip(), "EXISTS", f"Replicated procedure missing on {target}")

            # Approve candidate package for execution
            run_docker_exec(target, f"node /opt/taskand/bin/taskand approve {self.PROC_URI}")

    def test_04_multi_node_distributed_execution_and_receipt_validation(self):
        """Execute the procedure concurrently across all 3 nodes and validate node-specific receipts."""
        results = {}
        for node_container, expected_name in [
            ("taskand-node1", "taskand-node1"),
            ("taskand-node2", "taskand-node2"),
            ("taskand-node3", "taskand-node3"),
        ]:
            code, out, err = run_docker_exec(
                node_container,
                f"node /opt/taskand/bin/taskand --json proc {self.PROC_URI}",
            )
            self.assertEqual(code, 0, f"Execution failed on {node_container}: {err}\n{out}")
            data = json.loads(out)
            self.assertTrue(data.get("ok"), f"Response on {node_container} was not ok: {data}")
            self.assertEqual(data.get("node"), expected_name)
            self.assertEqual(data.get("status"), "HEALTHY")
            self.assertEqual(data.get("audit_id"), 42)
            self.assertTrue(data.get("receipt_success"))
            self.assertTrue(data.get("paxlet_digest", "").startswith("sha256:"))
            results[expected_name] = data

        self.assertEqual(len(results), 3, "Not all cluster nodes reported back successfully")


if __name__ == "__main__":
    unittest.main()
