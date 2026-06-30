#!/bin/bash
# entrypoint.sh - Starts the native Ollama backend and the Python proxy layer

if [ "${DISABLE_PROXY}" = "true" ]; then
  echo "Proxy explicitly disabled via DISABLE_PROXY=true."
  echo "Running vanilla Ollama on port 11434..."
  export OLLAMA_HOST=0.0.0.0:11434
  exec /usr/bin/ollama serve
fi

echo "Starting Ollama backend on port 11434..."
# Ollama runs on 11434, exposed to the host and Traefik
export OLLAMA_HOST=0.0.0.0:11434
/usr/bin/ollama serve &

# Wait briefly for Ollama to spin up
sleep 2

echo "Starting Ollama-Plus Python Proxy on port 11435..."
if [ -f /root/.ollama/tools/proxy.py ]; then
  # Execute the FastAPI proxy using the virtual environment created in the Dockerfile
  exec /opt/proxy_venv/bin/python /root/.ollama/tools/proxy.py
else
  echo "CRITICAL: Proxy script not found at /root/.ollama/tools/proxy.py!"
  echo "Please ensure you have mounted ./ollama/tools in docker-compose.yml"
  echo "Falling back to vanilla Ollama on port 11434..."
  exec /usr/bin/ollama serve
fi
