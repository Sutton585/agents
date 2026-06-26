#!/bin/bash

# Tell Ollama to listen on 11435 instead of its default port
export OLLAMA_HOST="127.0.0.1:11435"

# 1. Start Ollama in the background
/usr/bin/ollama serve &

# Give Ollama a second to initialize its server
sleep 2

# 2. Start your proxy script in the foreground.
# We use 'exec' so the Python script takes PID 1. If the proxy crashes, 
# the container restarts, keeping the system self-healing.
echo "Starting Proxy Layer..."
exec /opt/proxy_venv/bin/python /root/.ollama/tools/proxy.py