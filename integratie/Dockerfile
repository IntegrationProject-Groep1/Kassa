FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Kopieer de rest van de actuele code naar de container
COPY . .

# Start met een simpele keep-alive loop zodat het team de bestanden kan ontwikkelen
CMD ["python", "main.py"]
