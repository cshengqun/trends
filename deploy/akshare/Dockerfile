ARG BASE_IMAGE=python:3.12-slim-bookworm
FROM ${BASE_IMAGE}

WORKDIR /app
ENV PYTHONUNBUFFERED=1
COPY services/data-pipeline/requirements.txt /tmp/requirements.txt
COPY services/data-pipeline/requirements-akshare.txt /tmp/requirements-akshare.txt
RUN python -m pip install --no-cache-dir -r /tmp/requirements.txt -r /tmp/requirements-akshare.txt
COPY services/data-pipeline/akshare_sync.py /app/services/data-pipeline/akshare_sync.py
COPY services/data-pipeline/publish_akshare.py /app/services/data-pipeline/publish_akshare.py
COPY services/data-pipeline/sync_weekly_prices.py /app/services/data-pipeline/sync_weekly_prices.py
COPY services/data-pipeline/data/disclosures.json /app/services/data-pipeline/data/disclosures.json

USER 65534:65534
ENTRYPOINT ["python", "/app/services/data-pipeline/akshare_sync.py"]
