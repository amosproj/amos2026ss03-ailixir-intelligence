# Slim image: the pipeline is PubMed + arXiv + YouTube transcripts only — pure
# HTTP + PDF parsing, so no browser or ffmpeg is needed.
#
# Build context is THIS directory (the pipeline root), not Backend/:
#   docker build -t gcr.io/<project>/ailixir-scraper:<tag> .
FROM python:3.11-slim

# The slim image defaults to the C/POSIX locale, so Python picks ascii for
# stdout/file writes and blows up on non-ASCII scraped text (e.g. em-dashes).
# Force UTF-8 mode so all I/O is UTF-8 regardless of the container locale.
ENV PYTHONUTF8=1 \
    PYTHONIOENCODING=utf-8

WORKDIR /app

# Install Python deps first so the layer cache survives code-only changes.
# google-cloud-storage is only used by run_monthly.py for GCS state sync and is
# intentionally not part of the pipeline's own requirements.txt.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt google-cloud-storage

# App code, curated CSV inputs, and the committed data/*/index.json seeds that
# the scraper modules read at import time. .dockerignore keeps .env, raw dirs,
# the vosk model, logs, and terraform/ out of the image.
COPY . .

# Cloud Run Jobs run to completion — there is no server or port to expose.
CMD ["python", "run_monthly.py"]
