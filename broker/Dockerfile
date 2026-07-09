FROM python:3.10-slim

USER root

WORKDIR /app

COPY broker/aptfile /app/broker/aptfile
RUN apt-get update && \
    xargs -a broker/aptfile apt-get install -y && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

COPY broker/requirements.txt /app/broker/requirements.txt
RUN pip install --no-cache-dir -r broker/requirements.txt

COPY common /app/common
RUN pip install -e common

COPY . /app

ENTRYPOINT exec uvicorn broker.main:app --host 0.0.0.0 --port 8000 --reload
