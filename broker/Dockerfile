FROM python:3.10-slim

USER root

WORKDIR /app

RUN apt-get update && apt-get install -y iputils-ping

COPY requirements.txt /app/requirements.txt

RUN pip install --no-cache-dir -r /app/requirements.txt

COPY . /app/

RUN chmod +x /app/start.sh

CMD ["/app/start.sh"]
