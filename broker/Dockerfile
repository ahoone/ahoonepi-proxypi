FROM python:3.10-slim

USER root

WORKDIR /app

COPY requirements.txt /app/requirements.txt

RUN pip install --no-cache-dir -r /app/requirements.txt

COPY . /app/

RUN chmod +x /app/start.sh

CMD ["/app/start.sh"]
