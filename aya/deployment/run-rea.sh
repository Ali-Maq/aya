#!/usr/bin/env bash
set -euo pipefail
aya_root="$(cd "$(dirname "$0")/.." && pwd)"
exec uvx mcp-proxy@0.13.0 --host 127.0.0.1 --port 8766 -- \
  docker run --rm --name aya-rea --network none --read-only \
  --cap-drop ALL --security-opt no-new-privileges --pids-limit 256 \
  --memory 3g --cpus 4 --tmpfs /tmp:rw,size=2g,mode=1777 \
  -v "$aya_root/.state/reference:/reference:ro" \
  -e GHIDRA_INSTALL_DIR=/opt/ghidra \
  -e REA_MCP_OUTPUT_SCHEMA_PROFILE=off -e REA_MCP_INPUT_SCHEMA_PROFILE=compact \
  -i --entrypoint /opt/rea/node_modules/.bin/rea aya-rea:6.5.0 mcp
