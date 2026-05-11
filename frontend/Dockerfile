FROM python:3.14-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY frontend/pyproject.toml frontend/uv.lock ./frontend/
RUN uv sync --project frontend --no-dev --locked
COPY src/ ./src/
COPY frontend/ ./frontend/
ENV PYTHONPATH=/app
EXPOSE 8501
CMD ["sh", "-c", "uv run --project frontend streamlit run frontend/streamlit_app.py --server.port=${PORT:-8501} --server.address=0.0.0.0"]
