FROM python:3.11-slim

WORKDIR /app

# Install pipeline dependencies
COPY full_pipeline/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Copy document-extraction service (folder name has hyphen; map to valid module name)
COPY document-extraction/ /app/document-extraction/

# Copy the pipeline script
COPY full_pipeline/graphiti_pipeline.py /app/full_pipeline/graphiti_pipeline.py

# Images will be bind-mounted at runtime (see docker-compose volumes)
RUN mkdir -p /app/Images

WORKDIR /app/full_pipeline

CMD ["python", "graphiti_pipeline.py"]
