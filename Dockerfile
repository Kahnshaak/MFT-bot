FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    curl \
    netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code and scripts
COPY src/ ./src/
COPY scripts/ ./scripts/
COPY .env.example ./

# Copy .env file if it exists (for local development)
COPY .env* ./

# Create necessary directories
RUN mkdir -p /app/logs

# Set Python path
ENV PYTHONPATH=/app/src

# Add health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import sys; sys.path.append('/app/src'); \
    from core.startup_validator import StartupValidator; \
    import asyncio; \
    try: \
        result = asyncio.run(StartupValidator().validate_all()); \
        exit(0 if result[0] else 1); \
    except Exception as e: \
        print(f'Health check failed: {e}'); \
        exit(1);" || exit 1

# Make entrypoint script executable and use it
RUN chmod +x scripts/docker-entrypoint.sh

# Use the entrypoint script
ENTRYPOINT ["./scripts/docker-entrypoint.sh"]
