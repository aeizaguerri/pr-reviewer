FROM python:3.14-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY backend/pyproject.toml ./backend/pyproject.toml
RUN uv sync --project backend --no-dev
COPY src/ ./src/
COPY prompts/ ./prompts/
COPY backend/ ./backend/
EXPOSE 8000
CMD ["sh", "-c", "uv run --project backend uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
