FROM python:3.11-slim

# Install system deps for cairosvg
RUN apt-get update && apt-get install -y --no-install-recommends \
    libcairo2 libcairo2-dev libffi-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 10000
CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:10000", "--timeout", "120", "--workers", "2"]
