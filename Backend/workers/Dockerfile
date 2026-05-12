FROM python:3.11-slim

WORKDIR /app

# Install dependencies first so Docker layer cache is reused on code-only changes
COPY workers/requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Copy the full Backend context so shared/ is importable
COPY . .

EXPOSE 8080

CMD ["uvicorn", "workers.main:app", "--host", "0.0.0.0", "--port", "8080"]
