#!/bin/bash
set -e

# Initialize PostgreSQL if it's not already initialized
if [ ! -d "/var/lib/postgresql/14/main" ]; then
  su - postgres -c "/usr/lib/postgresql/14/bin/initdb -D /var/lib/postgresql/14/main"
fi

# Configure PostgreSQL to accept remote connections
su - postgres -c "sed -i \"s/#listen_addresses = 'localhost'/listen_addresses = '*'/\" /etc/postgresql/14/main/postgresql.conf"
su - postgres -c "echo 'host all all 0.0.0.0/0 md5' >> /etc/postgresql/14/main/pg_hba.conf"

# Start PostgreSQL
service postgresql start

# Create schema if it doesn't exist
su - postgres -c "psql -c \"ALTER USER postgres WITH PASSWORD 'password';\""
su - postgres -c "psql -c \"CREATE SCHEMA IF NOT EXISTS data;\""

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
   }
 }
}
EOL

# Start MindsDB with the custom config
exec python -m mindsdb --config=/root/mindsdb_config.json