FROM python:3.10-slim

USER root

WORKDIR /app

COPY aptfile .
RUN apt-get update && \
    xargs -a aptfile apt-get install -y && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chmod +x start.sh
CMD ["/app/start.sh"]
