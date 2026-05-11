FROM python:3.11-slim

LABEL maintainer="Virometrics Team"
LABEL description="Virometrics bioinformatics platform with Flask API"

# Environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_BREAK_SYSTEM_PACKAGES=1

# Working directory
WORKDIR /app

# Install system dependencies for bioinformatics tools
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    make \
    cmake \
    libffi-dev \
    libssl-dev \
    libhdf5-dev \
    libblas-dev \
    liblapack-dev \
    gfortran \
    graphviz \
    curl \
    wget \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# Install additional bioinformatics and queue dependencies
RUN pip install \
    rq \
    redis \
    psutil \
    celery \
    flask-restx

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p \
    /app/data/uploads \
    /app/data/outputs \
    /app/data/checkpoints \
    /app/data/logs

# Default port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# Default command
CMD ["python", "app.py"]
