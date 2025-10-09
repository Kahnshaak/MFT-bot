FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code and scripts
COPY src/ ./src/
COPY scripts/ ./scripts/

# Copy .env file if it exists (for local development)
COPY .env* ./

# Create necessary directories
RUN mkdir -p /app/logs

# Set Python path
ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1

# Simple health check
HEALTHCHECK --interval=60s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import discord; print('Bot dependencies OK')" || exit 1

# Make entrypoint script executable and use it
RUN chmod +x scripts/docker-entrypoint.sh

# Use the entrypoint script
ENTRYPOINT ["./scripts/docker-entrypoint.sh"]
