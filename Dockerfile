FROM node:24-bookworm-slim AS web
WORKDIR /build
ENV NEXT_TELEMETRY_DISABLED=1
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci
COPY apps/web/ ./
RUN npm run build

FROM golang:1.24-bookworm AS api
WORKDIR /build
COPY apps/api/go.mod apps/api/go.sum ./
RUN go mod download
COPY apps/api/ ./
RUN CGO_ENABLED=0 go build -trimpath -o /out/trends-api .

FROM node:24-bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-venv tini ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY services/data-pipeline/requirements.txt /tmp/requirements.txt
RUN python3 -m venv /opt/venv && /opt/venv/bin/pip install --no-cache-dir -r /tmp/requirements.txt
COPY --from=web /build/.next/standalone/ ./web/
COPY --from=web /build/.next/static/ ./web/.next/static/
COPY --from=api /out/trends-api /usr/local/bin/trends-api
COPY database/migrations/ ./database/migrations/
COPY services/data-pipeline/ ./services/data-pipeline/
COPY deploy/start.py ./start.py
RUN mkdir -p /app/web/.next/cache && chown -R node:node /app/web/.next/cache
ENV PORT=8080 NEXT_TELEMETRY_DISABLED=1 PYTHONUNBUFFERED=1
EXPOSE 8080
USER node
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["/opt/venv/bin/python", "/app/start.py"]
