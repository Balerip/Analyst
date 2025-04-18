#!/bin/bash
echo "Starting Ollama server..."
ollama serve &
OLLAMA_PID=$!

# Better health check for Ollama API
echo "Waiting for Ollama API to be ready..."
MAX_RETRIES=30
RETRY_COUNT=0
while ! curl -s http://localhost:11434/api/tags >/dev/null 2>&1; do
  if [ $RETRY_COUNT -ge $MAX_RETRIES ]; then
    echo "Ollama API failed to start after $MAX_RETRIES retries. Exiting."
    exit 1
  fi
  echo "Waiting for Ollama API to be available... ($RETRY_COUNT/$MAX_RETRIES)"
  sleep 2
  RETRY_COUNT=$((RETRY_COUNT+1))
done

echo "Pulling LLaMA model..."
ollama pull llama2

echo "Starting MindsDB..."
exec python -m mindsdb --api=http://0.0.0.0:47334