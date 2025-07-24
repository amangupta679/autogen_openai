#!/bin/bash

echo "[INFO] Bootstrapping container startup..."

echo "[INFO] Running code fix pipeline..."
python3 esql_handler_agent/agents/agent.py

echo "[INFO] Done."
