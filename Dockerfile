# API Key Scanner - Dockerfile
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy application files then install the package (console script: aikeyscan)
COPY . .
RUN pip install --no-cache-dir .

# Create volume mount points
VOLUME ["/app/data"]

# Environment variables
ENV PYTHONUNBUFFERED=1 \
    DB_PATH=/app/data/leaked_keys.db

# Expose web dashboard port
EXPOSE 5000

# Default command (can be overridden)
CMD ["aikeyscan", "scan"]
