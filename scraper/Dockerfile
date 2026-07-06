FROM python:3.10-slim

USER root

WORKDIR /app
COPY . /app

RUN apt-get update && \
    xargs -a scraper/aptfile apt-get install -y --no-install-recommends && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir -r scraper/requirements.txt
RUN pip install -e common

RUN ARCH=$(dpkg --print-architecture) && \
    if [ "$ARCH" = "amd64" ]; then \
        wget -q -O /tmp/google-chrome-stable_current_amd64.deb \
            https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb && \
        apt-get update && \
        apt-get install -y /tmp/google-chrome-stable_current_amd64.deb && \
        rm /tmp/google-chrome-stable_current_amd64.deb && \
        CHROME_VERSION=$(google-chrome --version | awk '{print $3}') && \
        CHROME_MAJOR=$(echo $CHROME_VERSION | cut -d. -f1) && \
        CHROMEDRIVER_VERSION=$(curl -s "https://googlechromelabs.github.io/chrome-for-testing/LATEST_RELEASE_$CHROME_MAJOR") && \
        wget -q -O /tmp/chromedriver-linux64.zip \
            "https://storage.googleapis.com/chrome-for-testing-public/$CHROMEDRIVER_VERSION/linux64/chromedriver-linux64.zip" && \
        unzip /tmp/chromedriver-linux64.zip -d /tmp/ && \
        mv /tmp/chromedriver-linux64/chromedriver /usr/local/bin/ && \
        chmod +x /usr/local/bin/chromedriver && \
        rm -f /tmp/chromedriver*.zip; \
    elif [ "$ARCH" = "arm64" ]; then \
        apt-get update && \
        apt-get install -y chromium chromium-driver && \
        ln -s /usr/bin/chromium /usr/bin/chromium-browser; \
    else \
        exit 1; \
    fi && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

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
