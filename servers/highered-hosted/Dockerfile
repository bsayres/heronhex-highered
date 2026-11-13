# Build from the repository root so the five server projects are in the context:
#   docker build -f servers/highered-hosted/Dockerfile -t heronhex-highered .
# The build pre-warms the cache, so the image ships with every bulk file already parsed and no first user waits for a download.
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.11.8 /uv /uvx /bin/
ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1 PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

WORKDIR /app
COPY servers/ /app/servers/
WORKDIR /app/servers/highered-hosted
RUN uv sync --locked --no-dev --no-editable

ENV HIGHERED_MCPS_CACHE=/app/cache \
    PATH="/app/servers/highered-hosted/.venv/bin:$PATH" \
    PORT=8080
# The operator's contact address for BLS bulk files (a public support mailbox, not a secret). Keys are not needed to pre-warm.
ARG HIGHERED_MCPS_CONTACT=mcp-support@heronhex.com
RUN HIGHERED_MCPS_CONTACT=$HIGHERED_MCPS_CONTACT highered-hosted-prewarm

RUN useradd --system --no-create-home --shell /usr/sbin/nologin app && chown -R app:app /app/cache
USER app
EXPOSE 8080
CMD ["highered-hosted"]
