# One image for both services: `app` (uvicorn) and `worker` (python -m sabq.worker).
# Build context is the repository root (so catalog/ can be included later).

FROM python:3.12-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.10.10 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /srv/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --locked --no-dev --no-install-project
COPY backend/ ./
RUN uv sync --locked --no-dev

FROM python:3.12-slim
ENV PATH="/srv/backend/.venv/bin:$PATH" PYTHONUNBUFFERED=1 TZ=UTC
RUN useradd --system --uid 10001 sabq
WORKDIR /srv/backend
COPY --from=build --chown=sabq:sabq /srv/backend /srv/backend
COPY --chown=sabq:sabq catalog/ /srv/catalog/
USER sabq
EXPOSE 8000
# Only the proxy can reach the app (no published port in production), so its
# X-Forwarded-For is trusted: login rate limits see the real client address.
CMD ["uvicorn", "sabq.app:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", \
     "--forwarded-allow-ips", "*"]
