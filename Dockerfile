ARG NODE_IMAGE=node:24-bookworm-slim
ARG GO_IMAGE=golang:1.24-bookworm

FROM ${NODE_IMAGE} AS web
ARG TRENDS_BASE_PATH=
ARG NPM_REGISTRY=https://registry.npmjs.org
WORKDIR /build
ENV NEXT_TELEMETRY_DISABLED=1 NEXT_PUBLIC_BASE_PATH=${TRENDS_BASE_PATH}
COPY apps/web/package.json apps/web/package-lock.json ./
RUN --mount=type=bind,source=deploy,target=/build-input \
    if [ -d /build-input/.build-cache/npm ]; then \
      cp -a /build-input/.build-cache/npm /tmp/trends-npm-cache \
      && npm ci --offline --cache /tmp/trends-npm-cache --no-audit --no-fund \
      && rm -rf /tmp/trends-npm-cache; \
    else \
      npm ci --registry="$NPM_REGISTRY" --no-audit --no-fund; \
    fi
COPY apps/web/ ./
RUN npm run build

FROM ${GO_IMAGE} AS api
ARG GO_PROXY=https://proxy.golang.org,direct
WORKDIR /build
ENV GOPROXY=${GO_PROXY}
COPY apps/api/go.mod apps/api/go.sum ./
RUN go mod download
COPY apps/api/ ./
RUN CGO_ENABLED=0 go build -trimpath -o /out/trends-api .

FROM ${NODE_IMAGE}
ARG TRENDS_BASE_PATH=
ARG DEBIAN_MIRROR=
RUN if [ -n "$DEBIAN_MIRROR" ]; then \
      sed -i "s|http://deb.debian.org|$DEBIAN_MIRROR|g" /etc/apt/sources.list.d/debian.sources; \
    fi \
    && apt-get update && apt-get install -y --no-install-recommends python3 python3-venv tini ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY services/data-pipeline/requirements.txt /tmp/requirements.txt
RUN --mount=type=bind,source=deploy,target=/build-input \
    python3 -m venv /opt/venv \
    && if [ -d /build-input/.build-cache/wheels ]; then \
      /opt/venv/bin/pip install --no-index --find-links=/build-input/.build-cache/wheels -r /tmp/requirements.txt; \
    else \
      /opt/venv/bin/pip install --no-cache-dir -r /tmp/requirements.txt; \
    fi
COPY --from=web /build/.next/standalone/ ./web/
COPY --from=web /build/.next/static/ ./web/.next/static/
COPY --from=api /out/trends-api /usr/local/bin/trends-api
COPY database/migrations/ ./database/migrations/
COPY services/data-pipeline/ ./services/data-pipeline/
COPY deploy/start.py ./start.py
RUN mkdir -p /app/web/.next/cache && chown -R node:node /app/web/.next/cache
ENV PORT=8080 NEXT_TELEMETRY_DISABLED=1 PYTHONUNBUFFERED=1 NEXT_PUBLIC_BASE_PATH=${TRENDS_BASE_PATH}
EXPOSE 8080
USER node
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["/opt/venv/bin/python", "/app/start.py"]
