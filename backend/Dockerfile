FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
RUN pip install --no-cache-dir uv==0.7.20
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY tollgate ./tollgate
RUN uv sync --frozen --no-dev
ENV PATH="/app/.venv/bin:$PATH"
RUN useradd -m -u 10001 tollgate && mkdir -p /data && chown tollgate /data
USER tollgate
EXPOSE 8000
CMD ["uvicorn", "tollgate.api:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
