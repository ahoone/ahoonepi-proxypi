FROM python:3.10-slim

USER root

WORKDIR /app
COPY . /app

RUN apt-get update && \
    xargs -a broker/aptfile apt-get install -y && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir -r broker/requirements.txt
RUN pip install -e common

ENTRYPOINT exec uvicorn broker.main:app --host 0.0.0.0 --port 8000 --reload
