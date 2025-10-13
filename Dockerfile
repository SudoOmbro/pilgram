# Use official Python 3.12 base image
FROM python:3.12-slim

# Prevent .pyc files and ensure unbuffered logs
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set working directory
WORKDIR /app

# Install system packages required for building pysqlite3
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libsqlite3-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency list first (to leverage build cache)
COPY requirements.txt .

# Update pip and install dependencies
RUN pip install --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# Copy all application files (including settings.json)
COPY . .

# Verify that settings.json exists during build
RUN if [ ! -f settings.json ]; then \
        echo "❌ ERROR: settings.json not found! Please create it from settings_template.json before building."; \
        exit 1; \
    fi

# Default command to run the app
CMD ["python", "main.py"]