FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    libcairo2 \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock .
RUN uv sync --no-dev --frozen --no-cache

COPY archivum/ archivum/

# Run as non-root
RUN useradd -m -u 10001 app

# Create required data directories
RUN mkdir -p /data/wiki /data/raw /data/kuzu \
  && chown -R app:app /data

USER app

EXPOSE 8000
EXPOSE 8001

CMD ["uvicorn", "archivum.main:app", "--host", "0.0.0.0", "--port", "8000"]
