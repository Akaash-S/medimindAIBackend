FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose port (internal only — Nginx container proxies to this port)
# Port 8000 is NOT published to the host; access is via the nginx service.
EXPOSE 8000

# Run with Gunicorn + Uvicorn workers
# CORS is handled upstream by Nginx — the FastAPI CORS middleware acts as a
# last-resort fallback only for requests that bypass the gateway.
CMD ["gunicorn", "app.main:app", \
     "-k", "uvicorn.workers.UvicornWorker", \
     "-w", "4", \
     "--bind", "0.0.0.0:8000", \
     "--timeout", "120", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]
