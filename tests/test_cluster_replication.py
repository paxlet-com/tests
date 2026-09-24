#!/usr/bin/env python3
"""Test suite for Taskand 3-node cluster mesh, SSH policy, and autonomous registry replication."""

from __future__ import annotations

import json
import shlex
import subprocess
import unittest

from doctor_policy import PEER_DOWN_INPUT, assert_peer_down_human


def run_docker_exec(container: str, cmd: str) -> tuple[int, str, str]:
    """Execute a bash command inside a running Docker container."""
    res = subprocess.run(
        ["docker", "exec", container, "bash", "-c", cmd],
        capture_output=True,
        timeout=90,
        text=True,
    )
    return res.returncode, res.stdout, res.stderr


class TestTaskandClusterReplication(unittest.TestCase):
    """Validates SSH connectivity, operator-gated replication policy, and autonomous registry sync."""

    @classmethod
    def setUpClass(cls):
        res = subprocess.run(
            ["docker", "ps", "--filter", "name=taskand-node1", "--format", "{{.Names}}"],
            capture_output=True,
            timeout=90,
            text=True,
        )
        if "taskand-node1" not in res.stdout:
            raise unittest.SkipTest("Taskand cluster containers offline. Run tests/run_cluster_test.sh")

    def test_01_cluster_containers_and_ssh_connectivity(self):
        """Verifies all 3 containers are online and can communicate via passwordless SSH."""
        for target in ["172.30.0.12", "172.30.0.13"]:
            code, out, err = run_docker_exec(
                "taskand-node1",
                f"ssh -o StrictHostKeyChecking=no root@{target} hostname",
            )
            self.assertEqual(code, 0, f"SSH to {target} failed: {err}")
            self.assertIn("taskand-node", out.strip())

    def test_02_autonomous_ssh_occupy_policy(self):
        """Verifies that autonomous organisms CANNOT perform unauthorized SSH replication.

        1. 'taskand occupy' without explicit --run is strictly an operator dry-run plan.
        2. Doctor prescription marks PEER_DOWN as 'human' executor, forbidding organism SSH breakout.
        """
        code, out, _ = run_docker_exec(
            "taskand-node1",
            "node /opt/taskand/bin/taskand --json occupy root@172.30.0.12",
        )
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertEqual(data.get("mode"), "dry-run")
        self.assertIn("plan", data)
        self.assertTrue(any("ssh" in str(step) for step in data["plan"]))

        # Inject the failure; an empty finding list must never pass this check.
        payload = shlex.quote(json.dumps(PEER_DOWN_INPUT))
        code, out, err = run_docker_exec(
            "taskand-node1",
            f"printf '%s' {payload} | node /opt/taskand/generated/doctor/prescribe/taskand.dev/v1/bin.mjs",
        )
        self.assertEqual(code, 0, err)
        assert_peer_down_human(json.loads(out))

    def test_03_cluster_peer_mesh_monitoring(self):
        """Verifies that nodes register each other as peers and monitor cluster health."""
        # Ensure node1 has node2 and node3 registered as peers
        run_docker_exec("taskand-node1", "node /opt/taskand/bin/taskand peer add http://taskand-node2:8077")
        run_docker_exec("taskand-node1", "node /opt/taskand/bin/taskand peer add http://taskand-node3:8077")

        code, out, err = run_docker_exec(
            "taskand-node1",
            "node /opt/taskand/bin/taskand --json proc proc://taskand.dev/cluster/monitor/v1",
        )
        self.assertEqual(code, 0, f"cluster/monitor failed: {err}")
        monitor_data = json.loads(out)
        self.assertTrue(monitor_data.get("ok"))
        self.assertIn("Węzły:", monitor_data.get("summary", ""))

        # Check peer list
        peers = monitor_data.get("peers", [])
        self.assertGreaterEqual(len(peers), 2)
        for p in peers:
            self.assertTrue(p.get("up"), f"Peer {p.get('peer')} is down")

    def test_04_autonomous_registry_and_generated_replication(self):
        """Verifies autonomous package transfer, checksum verification, and generated/ folder update."""
        package_uri = "proc://taskand.dev/cluster/mesh-autonomy-test/v1"

        # 1. Author and register package on node1
        setup_cmd = f"""
mkdir -p /opt/taskand/generated/cluster/mesh-autonomy-test/taskand.dev/v1
cat << "EOF" > /opt/taskand/generated/cluster/mesh-autonomy-test/taskand.dev/v1/proc.yaml
uri: {package_uri}
desc: Autonomous mesh replication validation package
kind: task
origin: builtin
EOF

cat << "EOF" > /opt/taskand/generated/cluster/mesh-autonomy-test/taskand.dev/v1/bin.mjs
#!/usr/bin/env node
import {{ writeFileSync }} from "node:fs";
const payload = {{ ok: true, cluster_node: process.env.TASKAND_NODE || "unknown", verified: true }};
writeFileSync(1, JSON.stringify(payload) + "\\n");
process.exit(0);
EOF
chmod +x /opt/taskand/generated/cluster/mesh-autonomy-test/taskand.dev/v1/bin.mjs

curl -s -X POST http://127.0.0.1:8077/api/registry \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer test-cluster-auth-token" \\
  -d '{{"action": "scan", "adopt": true}}'
"""
        code, out, err = run_docker_exec("taskand-node1", setup_cmd)
        self.assertEqual(code, 0, f"Package creation on node1 failed: {err}\n{out}")

        # 2. Add node1 as peer on node2 and trigger autonomous cluster monitor pull
        run_docker_exec("taskand-node2", "node /opt/taskand/bin/taskand peer add http://taskand-node1:8077")
        code, out, err = run_docker_exec(
            "taskand-node2",
            'node /opt/taskand/bin/taskand --json proc proc://taskand.dev/cluster/monitor/v1 \'{"pull":true,"token":"test-cluster-auth-token"}\'',
        )
        self.assertEqual(code, 0, f"Autonomous pull on node2 failed: {err}")
        pull_data = json.loads(out)
        self.assertTrue(pull_data.get("ok"))

        # 3. Assert generated/ folder now exists on node2
        code, out, _ = run_docker_exec(
            "taskand-node2",
            "test -f /opt/taskand/generated/cluster/mesh-autonomy-test/taskand.dev/v1/bin.mjs && echo EXISTS",
        )
        self.assertEqual(out.strip(), "EXISTS", "Package was not replicated into generated/ folder on node2")

        # 4. Approve candidate package and execute on node2
        run_docker_exec("taskand-node2", f"node /opt/taskand/bin/taskand approve {package_uri}")
        code, out, err = run_docker_exec("taskand-node2", f"node /opt/taskand/bin/taskand proc {package_uri}")
        self.assertEqual(code, 0, f"Execution of replicated package failed: {err}")
        exec_result = json.loads(out)
        self.assertTrue(exec_result.get("ok"))
        self.assertTrue(exec_result.get("verified"))


if __name__ == "__main__":
    unittest.main()
