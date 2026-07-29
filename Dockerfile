# API Key Scanner - Dockerfile
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Create volume mount points
VOLUME ["/app/data"]

# Environment variables
ENV PYTHONUNBUFFERED=1 \
    DB_PATH=/app/data/leaked_keys.db

# Expose web dashboard port
EXPOSE 5000

# Default command (can be overridden)
CMD ["python", "main_v2.2.py"]
