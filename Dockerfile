FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt /app/requirements.txt
COPY backend/ /app/backend/

RUN pip install --no-cache-dir -r /app/requirements.txt

WORKDIR /app/backend

EXPOSE 3000

CMD ["sh", "-c", "case \"${SERVICE_TYPE:-api}\" in \
    api) exec uvicorn main:app --host 0.0.0.0 --port \"${PORT:-3000}\" ;; \
    bot) exec python max_bot.py ;; \
    scheduler) exec python scheduler.py ;; \
    *) echo \"ERROR: Unknown SERVICE_TYPE '${SERVICE_TYPE}'\" >&2; exit 1 ;; \
    esac"]
