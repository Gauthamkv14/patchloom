# Pinned official Python slim image with deliberate version and multi-arch digest pinning
# Python 3.13 (Python 3.13.16 Debian slim), active security support through October 2029
FROM python:3.13-slim@sha256:70729b46c69b4f1e97c4822c1af3df53a1476cf5ddc6c087c0c10bc3a5678c2f

# Prevent bytecode generation and ensure unbuffered stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Create dedicated non-root unprivileged service user and group
RUN groupadd -g 10001 appuser && \
    useradd -u 10001 -g appuser -s /sbin/nologin -M appuser

# Install dependencies first for layer caching
COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r /app/requirements.txt

# Copy backend application source and test/demo fixtures
COPY backend/app /app/app
COPY fixtures /app/fixtures

# Ensure application files are owned by the non-root user
RUN chown -R appuser:appuser /app

# Run as non-root user
USER appuser

EXPOSE 8000

# Periodic health check using Python standard library (no external binaries required)
HEALTHCHECK --interval=15s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request, sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health').getcode() == 200 else 1)"

# Start FastAPI application via Uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
