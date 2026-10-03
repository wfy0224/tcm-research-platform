FROM ghcr.io/astral-sh/uv:0.8.22 AS uv
FROM python:3.12-slim
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY backend/ ./
RUN uv sync --frozen --no-dev && useradd --uid 10001 --create-home tcm \
    && mkdir -p /data /run/tcm-bootstrap && chown -R tcm:tcm /data /run/tcm-bootstrap
COPY deploy/container_entry.py deploy/queue_worker.py /app/deploy/
ENV PATH="/app/backend/.venv/bin:$PATH" PYTHONUNBUFFERED=1 TCM_DATA_ROOT=/data
USER tcm
ENTRYPOINT ["python", "/app/deploy/container_entry.py"]
CMD ["api"]
