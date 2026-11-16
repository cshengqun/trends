ARG BASE_IMAGE
FROM ${BASE_IMAGE}

USER root
WORKDIR /app
COPY services/data-pipeline/requirements-akshare.txt /tmp/requirements-akshare.txt
RUN /opt/venv/bin/pip install --no-cache-dir -r /tmp/requirements-akshare.txt
COPY services/data-pipeline/akshare_sync.py /app/services/data-pipeline/akshare_sync.py
COPY services/data-pipeline/data/disclosures.json /app/services/data-pipeline/data/disclosures.json

USER node
ENTRYPOINT ["/opt/venv/bin/python", "/app/services/data-pipeline/akshare_sync.py"]
