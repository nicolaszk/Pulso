FROM python:3.12-slim

WORKDIR /app/backend

# Dependências do backend e do motor (fila_cirurgica)
COPY backend/requirements.txt /tmp/requirements-backend.txt
COPY fila_cirurgica/requirements.txt /tmp/requirements-motor.txt
RUN pip install --no-cache-dir -r /tmp/requirements-backend.txt -r /tmp/requirements-motor.txt