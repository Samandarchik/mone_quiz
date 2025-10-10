# Dockerfile
FROM python:3.11-slim

# prevent python from writing .pyc files and enable stdout/stderr flush
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# System deps for building packages (kept minimal)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create data dir inside container (will be mounted by compose)
RUN mkdir -p /app/data

# Expose port
EXPOSE 8050

# Default command
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8050", "--proxy-headers"]
