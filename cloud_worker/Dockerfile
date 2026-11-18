FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY cloud_worker/requirements.txt /app/cloud_worker/requirements.txt
RUN pip install --no-cache-dir -r /app/cloud_worker/requirements.txt
COPY llm_api.py /app/llm_api.py
COPY cloud_worker /app/cloud_worker

CMD ["python", "-m", "cloud_worker.worker"]
