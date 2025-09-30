FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code and scripts
COPY src/ ./src/
COPY scripts/ ./scripts/
COPY .env.example ./

# Create necessary directories
RUN mkdir -p /app/logs

# Set Python path
ENV PYTHONPATH=/app/src

# Add health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import asyncio; from src.core.startup_validator import StartupValidator; \
    async def check(): \
        try: \
            validator = StartupValidator(); \
            success, _ = await validator.validate_all(); \
            exit(0 if success else 1); \
        except: exit(1); \
    asyncio.run(check())" || exit 1

# Run startup validation before starting bot
CMD ["sh", "-c", "python scripts/validate-env.py && python src/bot.py"]
