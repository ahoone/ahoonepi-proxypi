FROM python:3.10-slim

USER root

WORKDIR /app

COPY tests/requirements.txt /app/tests/requirements.txt
RUN pip install --no-cache-dir -r tests/requirements.txt

COPY common /app/common
RUN pip install -e common

COPY . /app/
