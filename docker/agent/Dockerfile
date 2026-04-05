FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    curl \
    snmp \
    libsnmp-dev \
    nmap \
    masscan \
    arp-scan \
    fprobe \
    nfdump \
    p0f \
    && rm -rf /var/lib/apt/lists/*

COPY services/agent/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY services/agent /app/agent
COPY services/common /app/services/common
COPY configs/agent.yaml /app/config/agent.yaml

RUN mkdir -p /app/data && \
    touch /app/__init__.py && \
    touch /app/services/__init__.py

ENV PYTHONPATH=/app
ENV AGENT_CONFIG_PATH=/app/config/agent.yaml

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

ENTRYPOINT ["python", "-m", "agent.main"]
CMD []
