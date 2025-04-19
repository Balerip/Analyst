#!/bin/bash
set -e
echo "Starting Ollama..."
ollama serve &

echo "Starting MindsDB..."
# Create a custom config file to force binding to all interfaces
cat > /root/mindsdb_config.json << EOL
{
  "api": {
    "http": {
      "host": "0.0.0.0",
      "port": "47334"
    },
    "mysql": {
      "host": "0.0.0.0",
      "port": "47335",
      "database": "mindsdb",
      "ssl": true
    }
  }
}
EOL

# Start MindsDB with the custom config
exec python -m mindsdb --config=/root/mindsdb_config.json