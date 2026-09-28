FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY alembic.ini alembic.ini
COPY backend backend
COPY config config
COPY demo demo
RUN chmod +x backend/entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["backend/entrypoint.sh"]
