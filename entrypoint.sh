#!/bin/bash

echo "Starting Ollama server..."
ollama serve &

# Wait for Ollama API to come up
sleep 15

echo "Pulling LLaMA model..."
ollama pull llama2

echo "Starting MindsDB..."
exec python -m mindsdb
