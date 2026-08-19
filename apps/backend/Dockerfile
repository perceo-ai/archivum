FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    nodejs \
    npm \
    libgomp1 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    libcairo2 \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv
RUN npm install -g @openai/codex @anthropic-ai/claude-code \
    && npm cache clean --force

COPY pyproject.toml uv.lock .
RUN uv sync --no-dev --frozen --no-cache

COPY archivum/ archivum/

# Run as non-root
RUN useradd -m -u 10001 app

# Create required data directories
RUN mkdir -p /data/wiki /data/raw /data/kuzu /home/app/.codex /home/app/.claude \
  && chown -R app:app /data /home/app/.codex /home/app/.claude

USER app

EXPOSE 8000
EXPOSE 8001

CMD ["uvicorn", "archivum.main:app", "--host", "0.0.0.0", "--port", "8000"]
