FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    curl \
    snmp \
    libsnmp-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for caching
COPY services/agent/requirements.txt /app/requirements.txt

# Install Python dependencies
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy application code
COPY services/agent /app

# Create config directory
RUN mkdir -p /app/config /app/data

# Copy default config
COPY configs/agent.yaml /app/config/agent.yaml

# Expose port
EXPOSE 8080

# Run the agent
CMD ["python", "-m", "agent.main"]
