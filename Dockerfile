FROM python:3.14-slim

ENV UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

RUN pip install --no-cache-dir uv==0.11.29

WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY src ./src
RUN uv sync --frozen --no-dev --no-editable

# Runs as a non-root user that can write only to its data volume.
RUN useradd --create-home --uid 1000 bot \
    && mkdir /data \
    && chown bot:bot /data
USER bot
VOLUME /data

CMD ["/app/.venv/bin/python", "-m", "reminder_bot"]
