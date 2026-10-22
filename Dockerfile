FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Dependencias del sistema para PostgreSQL (psycopg[binary] incluye binarios)
RUN apt-get update && apt-get install -y \
    libpq-dev \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt /app/
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

COPY . /app/

EXPOSE 8000