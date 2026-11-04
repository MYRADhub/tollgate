#!/usr/bin/env bash
# Pull the latest main on the server and rebuild what changed.
# Usage: HOST=root@<ip> ./deploy/update.sh
set -euo pipefail
: "${HOST:?set HOST=root@<server-ip>}"
ssh "$HOST" 'cd /opt/tollgate && git pull -q --ff-only && cd deploy && docker compose up -d --build 2>&1 | tail -3 && docker compose ps --format "table {{.Service}}\t{{.Status}}"'
