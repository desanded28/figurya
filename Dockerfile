FROM python:3.11-slim

WORKDIR /app

# Install dependencies first (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Port is provided by the platform via $PORT (Railway/Render) — fallback to 8000 locally
ENV PORT=8000
EXPOSE 8000

# Run with uvicorn — use shell form so $PORT is expanded at runtime
CMD uvicorn weebshelf.app:app --host 0.0.0.0 --port ${PORT}
