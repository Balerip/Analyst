# Base image
FROM python:3.10-slim
# Install dependencies
RUN apt-get update && apt-get install -y \
 git curl sudo gnupg unzip libgomp1 && \
 rm -rf /var/lib/apt/lists/*
# Install Ollama    
RUN curl -fsSL https://ollama.com/install.sh | sh
# Set working directory
WORKDIR /app
COPY . /app
# Install MindsDB (or your custom app)
RUN pip install --upgrade pip && pip install --no-cache-dir -e .[all]
RUN rm -rf ~/.cache/pip /root/.cache
# Expose both MindsDB ports
EXPOSE 47334 47335 11434
# Entrypoint
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
CMD ["/entrypoint.sh"]