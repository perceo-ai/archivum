FROM python:3.12-slim
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libffi-dev \
    libssl-dev \
    libxml2-dev \
    libxslt1-dev \
    zlib1g-dev \
    ffmpeg \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf2.0-0 \
    libcairo2 \
    && rm -rf /var/lib/apt/lists/*

RUN pip install uv

COPY pyproject.toml .
RUN uv sync --no-dev

COPY archivum/ archivum/

# Run as non-root
RUN useradd -m -u 10001 app \
  && chown -R app:app /app

# Create required data directories
RUN mkdir -p /data/wiki /data/raw /data/kuzu \
  && chown -R app:app /data

USER app

EXPOSE 8000
EXPOSE 8001

CMD ["uv", "run", "uvicorn", "archivum.main:app", "--host", "0.0.0.0", "--port", "8000"]
