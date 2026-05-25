FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY src /app/src
COPY README.md /app/README.md

ENTRYPOINT ["python3", "-m", "src.feed_router.cli"]
