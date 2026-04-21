FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first (better layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Cloud Run sets PORT env var (default 8080)
ENV PORT=8080

# Run uvicorn — binds to $PORT automatically
CMD uvicorn api.server:app --host 0.0.0.0 --port $PORT --workers 1 --log-level info
