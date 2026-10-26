FROM python:3.12.7-slim

ARG INSTALL_DEV=false
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt requirements-dev.txt ./
RUN pip install -r requirements.txt \
    && if [ "$INSTALL_DEV" = "true" ]; then pip install -r requirements-dev.txt; fi

RUN groupadd --system app && useradd --system --gid app --home /app app
COPY --chown=app:app . .
RUN chmod +x /app/docker-entrypoint.sh

USER app
EXPOSE 8000
ENTRYPOINT []
CMD ["/app/docker-entrypoint.sh", "web"]
