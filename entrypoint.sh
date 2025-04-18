#!/bin/bash
echo "Starting Ollama..."
ollama serve &

sleep 10
echo "Starting MindsDB..."
exec python -m mindsdb
