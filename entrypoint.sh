#!/bin/bash
set -e
echo "Starting MindsDB..."
# Correct environment variables for MindsDB
export MINDSDB_HTTP_HOST=0.0.0.0
export MINDSDB_HTTP_PORT=47334
export MINDSDB_APIS='http,mysql'
# Start MindsDB
exec python -m mindsdb