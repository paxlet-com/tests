#!/bin/bash
set -e

# Start SSH daemon
/usr/sbin/sshd

# Initialize node-local taskand copy if empty
if [ ! -f "/opt/taskand/bin/taskand" ] && [ -d "/opt/taskand-template" ]; then
    echo "[$(hostname)] Initializing local taskand workspace from template..."
    mkdir -p /opt/taskand
    cp -r /opt/taskand-template/. /opt/taskand/
fi

# Ensure TASKAND_BIND is 0.0.0.0 for cluster access
export TASKAND_BIND="${TASKAND_BIND:-0.0.0.0}"
if [ -z "${TASKAND_AUTH_TOKEN:-}" ]; then
    export TASKAND_AUTH_TOKEN="test-cluster-auth-token"
fi
if [ -z "${TASKAND_VAULT_KEY:-}" ]; then
    export TASKAND_VAULT_KEY="test-cluster-vault-key-hex"
fi

# If gateway.py is present and AUTO_START_GATEWAY is true, launch gateway in background
if [ "${AUTO_START_GATEWAY:-1}" = "1" ] && [ -f "/opt/taskand/gateway.py" ]; then
    echo "[$(hostname)] Starting Taskand Gateway on 0.0.0.0:8077..."
    cd /opt/taskand
    python3 /opt/taskand/gateway.py > /var/log/taskand-gateway.log 2>&1 &
fi

if [ "$#" -gt 0 ]; then
    exec "$@"
else
    exec tail -f /dev/null
fi
