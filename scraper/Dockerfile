FROM python:3.10-slim

USER root

WORKDIR /app

COPY scraper/aptfile /app/scraper/aptfile
RUN apt-get update && \
    xargs -a scraper/aptfile apt-get install -y --no-install-recommends

COPY scraper/requirements.txt /app/scraper/requirements.txt
RUN pip install --no-cache-dir -r scraper/requirements.txt

COPY common /app/common
RUN pip install -e common

ARG CHROMIUM_VERSION
ARG CHROMIUM_SNAPSHOT_DATE
RUN ARCH=$(dpkg --print-architecture) && \
    SNAPSHOT_BASE="https://snapshot.debian.org/archive/debian-security/${CHROMIUM_SNAPSHOT_DATE}/pool/updates/main/c/chromium" && \
    TMPDIR=$(mktemp -d) && \
    cd "$TMPDIR" && \
    for pkg in chromium chromium-common chromium-driver chromium-sandbox; do \
        curl -fsSLO "${SNAPSHOT_BASE}/${pkg}_${CHROMIUM_VERSION}_${ARCH}.deb"; \
    done && \
    apt-get update && \
    apt-get install -y ./*.deb && \
    ln -s /usr/bin/chromium /usr/bin/chromium-browser && \
    cd / && rm -rf "$TMPDIR"

RUN apt-get clean && \
    rm -rf /var/lib/apt/lists/*

COPY . /app
RUN groupadd -r chrome && useradd -r -g chrome -m chrome
RUN chown -R chrome:chrome /app

#######################################
# Changing container running user,
# as nodriver or zendriver may raise
# errors when running as root.
# Changing the sandbox parameter does
# not seem to solve the issue as indicated.
#######################################

USER chrome

ENTRYPOINT exec uvicorn scraper.main:app --host 0.0.0.0 --port 8000 --reload
