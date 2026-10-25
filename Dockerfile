FROM python:3.12-slim

# no .pyc files, unbuffered logs (each JSON log line appears immediately)
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 RECRUIT_DB=/data/recruitment.db

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app

# run as a non-root user; the database lives in a volume
RUN useradd --create-home appuser && mkdir -p /data && chown appuser /data
USER appuser
VOLUME /data
EXPOSE 8000

# RECRUIT_ADMIN_KEY must be supplied at run time:  docker run -e RECRUIT_ADMIN_KEY=... -p 8000:8000 recruitment-api
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
