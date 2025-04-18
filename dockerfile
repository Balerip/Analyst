FROM python:3.10-slim

# Install dependencies
RUN apt-get update && apt-get install -y \
    git curl sudo gnupg unzip libgomp1 && \
    rm -rf /var/lib/apt/lists/*

# Install Ollama
RUN curl -fsSL https://ollama.com/install.sh | bash
RUN ollama pull llama2

# Set working directory
WORKDIR /app
COPY . /app

# Install MindsDB
RUN pip install --upgrade pip && pip install -e .[all]

# Copy and run entrypoint
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
CMD ["/entrypoint.sh"]
