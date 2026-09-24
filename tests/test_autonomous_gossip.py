#!/usr/bin/env python3
"""Integration tests for Taskand autonomous background gossip and continuous registry replication.

Validates that cluster nodes continuously probe peers, discover new packages,
autonomously pull and approve them in the background without any manual trigger or operator intervention.
"""

from __future__ import annotations

import json
import subprocess
import time
import unittest
import urllib.request


def run_docker_exec(container: str, cmd: str) -> tuple[int, str, str]:
    """Execute a bash command inside a running Docker container."""
    res = subprocess.run(
        ["docker", "exec", container, "bash", "-c", cmd],
        capture_output=True,
        text=True,
    )
    return res.returncode, res.stdout, res.stderr


def fetch_http_json(url: str, token: str = "test-cluster-auth-token", timeout: float = 3.0) -> dict:
    """Fetch HTTP JSON endpoint with auth header."""
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


class TestTaskandAutonomousGossip(unittest.TestCase):
    """Validates real-time, autonomous background gossip discovery, continuous pulling and auto-approval."""

    BEACON_URI = "proc://taskand.dev/cluster/autonomous-beacon/v1"

    def test_01_gossip_service_active_on_all_nodes(self):
        """Verifies that all 3 cluster nodes have the background gossip service active."""
        ports = {"taskand-node1": 8071, "taskand-node2": 8072, "taskand-node3": 8073}
        for node_name, port in ports.items():
            url = f"http://127.0.0.1:{port}/api/cluster/gossip"
            data = fetch_http_json(url)
            self.assertTrue(data.get("ok"), f"Gossip API failed on {node_name}: {data}")
            self.assertTrue(data.get("running"), f"Gossip worker not running on {node_name}")
            self.assertIn("interval", data)
            self.assertTrue(data.get("auto_approve"), f"Auto-approve should be enabled on {node_name}")

    def test_02_author_and_register_package_on_node1(self):
        """Authors a new cluster beacon procedure on Node 1."""
        setup_cmd = f"""
mkdir -p /opt/taskand/generated/cluster/autonomous-beacon/taskand.dev/v1
cat << "EOF" > /opt/taskand/generated/cluster/autonomous-beacon/taskand.dev/v1/proc.yaml
uri: {self.BEACON_URI}
desc: Autonomous background gossip propagation beacon
kind: task
origin: builtin
env:
  - TASKAND_NODE
EOF

cat << "EOF" > /opt/taskand/generated/cluster/autonomous-beacon/taskand.dev/v1/bin.mjs
#!/usr/bin/env node
import {{ writeFileSync }} from "node:fs";
import {{ hostname }} from "node:os";
const payload = {{
  ok: true,
  node: hostname(),
  beacon: true,
  timestamp: new Date().toISOString()
}};
writeFileSync(1, JSON.stringify(payload) + "\\n");
process.exit(0);
EOF
chmod +x /opt/taskand/generated/cluster/autonomous-beacon/taskand.dev/v1/bin.mjs

curl -s -X POST http://127.0.0.1:8077/api/registry \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer test-cluster-auth-token" \\
  -d '{{"action": "scan", "adopt": true}}'
"""
        code, out, err = run_docker_exec("taskand-node1", setup_cmd)
        self.assertEqual(code, 0, f"Package registration failed on node1: {err}\n{out}")

        # Verify active on node1
        code, out, err = run_docker_exec("taskand-node1", f"node /opt/taskand/bin/taskand --json proc {self.BEACON_URI}")
        self.assertEqual(code, 0, f"Execution failed on node1: {err}\n{out}")
        data = json.loads(out)
        self.assertTrue(data.get("ok"))
        self.assertEqual(data.get("node"), "taskand-node1")

    def test_03_autonomous_propagation_via_background_gossip(self):
        """Verifies that Node 2 and Node 3 autonomously pull and approve the package WITHOUT manual pull triggers."""
        # Wait up to 10 seconds for the background gossip daemon (poll interval is 2s)
        replicated_node2 = False
        replicated_node3 = False

        start_time = time.time()
        while time.time() - start_time < 12.0:
            c2, out2, _ = run_docker_exec(
                "taskand-node2",
                "test -f /opt/taskand/generated/cluster/autonomous-beacon/taskand.dev/v1/bin.mjs && echo YES || echo NO",
            )
            c3, out3, _ = run_docker_exec(
                "taskand-node3",
                "test -f /opt/taskand/generated/cluster/autonomous-beacon/taskand.dev/v1/bin.mjs && echo YES || echo NO",
            )

            if out2.strip() == "YES":
                replicated_node2 = True
            if out3.strip() == "YES":
                replicated_node3 = True

            if replicated_node2 and replicated_node3:
                break
            time.sleep(1.0)

        self.assertTrue(replicated_node2, "Package was not autonomously replicated to taskand-node2 by gossip daemon")
        self.assertTrue(replicated_node3, "Package was not autonomously replicated to taskand-node3 by gossip daemon")

    def test_04_execution_on_replicated_nodes_and_gossip_status(self):
        """Executes the replicated procedure on node2 and node3 and inspects gossip receipts."""
        # Node 2 execution
        code2, out2, err2 = run_docker_exec(
            "taskand-node2",
            f"node /opt/taskand/bin/taskand --json proc {self.BEACON_URI}",
        )
        self.assertEqual(code2, 0, f"Execution failed on node2: {err2}\n{out2}")
        data2 = json.loads(out2)
        self.assertTrue(data2.get("ok"))
        self.assertEqual(data2.get("node"), "taskand-node2")
        self.assertTrue(data2.get("beacon"))

        # Node 3 execution
        code3, out3, err3 = run_docker_exec(
            "taskand-node3",
            f"node /opt/taskand/bin/taskand --json proc {self.BEACON_URI}",
        )
        self.assertEqual(code3, 0, f"Execution failed on node3: {err3}\n{out3}")
        data3 = json.loads(out3)
        self.assertTrue(data3.get("ok"))
        self.assertEqual(data3.get("node"), "taskand-node3")
        self.assertTrue(data3.get("beacon"))

        # Check CLI gossip command on node2
        code_cli, out_cli, _ = run_docker_exec("taskand-node2", "node /opt/taskand/bin/taskand --json gossip")
        self.assertEqual(code_cli, 0)
        cli_data = json.loads(out_cli)
        self.assertTrue(cli_data.get("ok"))
        self.assertTrue(cli_data.get("running"))
        self.assertIn(self.BEACON_URI, cli_data.get("synced_uris", []))


if __name__ == "__main__":
    unittest.main()
