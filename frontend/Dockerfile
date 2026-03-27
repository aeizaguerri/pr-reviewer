FROM python:3.14-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY frontend/pyproject.toml ./frontend/pyproject.toml
RUN uv sync --project frontend --no-dev
COPY frontend/ ./frontend/
EXPOSE 8501
CMD ["uv", "run", "--project", "frontend", "streamlit", "run", "frontend/streamlit_app.py", "--server.port=8501", "--server.address=0.0.0.0"]
