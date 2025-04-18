#!/bin/bash
set -e

echo "Starting MindsDB..."
# Bind to all interfaces so Docker host can access it
export MINDSDB_API_HOST=0.0.0.0

# Start MindsDB
exec python -m mindsdb
