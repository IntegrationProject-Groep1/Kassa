FROM python:3.12-slim

WORKDIR /app

# Copy requirements and install dependencies
COPY integratie/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the integration service code
COPY integratie/ .

# De toegewezen poort voor Kassa is 30030-30039
EXPOSE 30030

# Health check - verify Odoo can be reached
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python ping_odoo.py || exit 1

# Start the Order Poller service
CMD ["python", "main.py"]
