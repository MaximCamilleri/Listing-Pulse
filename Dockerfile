FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
ENV LOG_DIRECTORY=/app/logs
ENV POLL_HEALTHCHECK_FILE=/app/logs/poll-heartbeat
ENV POLL_HEALTHCHECK_GRACE_SECONDS=15

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --home-dir /app --no-create-home app \
    && mkdir -p /app/logs \
    && chown app:app /app/logs

COPY --chown=app:app main.py .
COPY --chown=app:app src ./src

USER 10001:10001

STOPSIGNAL SIGTERM

HEALTHCHECK --interval=15s --timeout=5s --start-period=60s --retries=3 \
    CMD python -m src.support.poll_healthcheck

CMD ["python", "main.py"]
