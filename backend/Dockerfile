FROM python:3.12-slim

# no .pyc files, unbuffered logs (each JSON log line appears immediately)
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UPLOAD_DIR=/data/uploads

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY migrations ./migrations
COPY alembic.ini seed.py ./

# run as a non-root user; uploaded resumes live in a volume
RUN useradd --create-home appuser && mkdir -p /data/uploads && chown -R appuser /data
USER appuser
VOLUME /data
EXPOSE 8000

# DATABASE_URL and JWT_SECRET are supplied at run time (docker-compose.yml / the host); migrations run on start
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
