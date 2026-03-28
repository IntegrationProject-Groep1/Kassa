FROM python:3.12-slim

WORKDIR /app

# Disable Python output buffering so logs appear immediately in docker logs
ENV PYTHONUNBUFFERED=1

COPY integratie/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Kopieer de rest van de actuele code naar de container
COPY integratie/ .

# De toegewezen poort voor Kassa is 30030-30039
EXPOSE 30030

# Start met een simpele keep-alive loop zodat het team de bestanden kan ontwikkelen
CMD ["python", "main.py"]
