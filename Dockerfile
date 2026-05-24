FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install the package. Pass --build-arg INSTALL_LLM=1 to bake in the OpenAI /
# Anthropic SDKs for a deployment that runs with MEDFUEL_USE_LLM=1.
ARG INSTALL_LLM=0
COPY pyproject.toml ./
COPY src ./src
RUN pip install --upgrade pip \
    && if [ "$INSTALL_LLM" = "1" ]; then pip install ".[llm]"; else pip install .; fi

# Default to a writable on-disk SQLite path; override MEDFUEL_DATABASE_URL with
# a Supabase/Postgres URL in production.
ENV MEDFUEL_DATABASE_URL=sqlite:////data/medfuel.sqlite
RUN mkdir -p /data

# Drop root for runtime.
RUN useradd --create-home --uid 10001 medfuel && chown -R medfuel /data /app
USER medfuel

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,os,sys; urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8000')+'/health'); " || exit 1

# PaaS platforms inject $PORT; default to 8000 locally.
CMD ["sh", "-c", "uvicorn medfuel.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
