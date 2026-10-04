# Build from repository root. AI logic only: no business data or DB client.
FROM python:3.12.10-slim-bookworm@sha256:fd95fa221297a88e1cf49c55ec1828edd7c5a428187e67b5d1805692d11588db AS runtime-base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY deploy/agentarts/requirements.lock /tmp/requirements.lock
RUN pip install --no-cache-dir --only-binary=:all: --require-hashes -r /tmp/requirements.lock
COPY backend/__init__.py ./backend/__init__.py
COPY backend/app/__init__.py backend/app/business_taxonomy.py ./backend/app/
COPY backend/business/ ./backend/business/
COPY backend/agent_runtime/ ./backend/agent_runtime/
COPY shared/business-taxonomy.json ./shared/business-taxonomy.json
USER 10001:10001
EXPOSE 8080
HEALTHCHECK --interval=15s --timeout=3s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/ping',timeout=2)"
FROM runtime-base AS matching
CMD ["python","-B","-m","uvicorn","backend.agent_runtime.matching_server:app","--host","0.0.0.0","--port","8080","--workers","1","--no-access-log"]

FROM runtime-base AS development
CMD ["python","-B","-m","uvicorn","backend.agent_runtime.development_server:app","--host","0.0.0.0","--port","8080","--workers","1","--no-access-log"]
