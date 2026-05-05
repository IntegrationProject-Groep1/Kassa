FROM python:3.12-slim

WORKDIR /app

# Disable Python output buffering so logs appear immediately in docker logs
ENV PYTHONUNBUFFERED=1

# Copy requirements and install dependencies
COPY integratie/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the integration service code
COPY integratie/ .

# De toegewezen poort voor Kassa is 30030-30039
EXPOSE 30030

# Health check - verify the service is fully started and Odoo is reachable
HEALTHCHECK --interval=10s --timeout=5s --start-period=10s --retries=30 \
    CMD [ -f /tmp/service_ready ] || exit 1

# Start the Order Poller service
CMD ["python", "main.py"]
