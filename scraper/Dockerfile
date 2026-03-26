FROM python:3.10-slim

USER root

RUN apt-get update && apt-get install -y \
    net-tools ffmpeg \
    wget gnupg xvfb ca-certificates \
    fonts-liberation libx11-xcb1 libxcomposite1 \
    libxcursor1 libxdamage1 libxext6 libxfixes3 \
    libxi6 libxrandr2 libxrender1 libxtst6 \
    libnss3 libatk1.0-0 libcups2 libdbus-1-3 \
    libdrm2 libgbm1 libasound2 libpangocairo-1.0-0 \
    libxshmfence1 lsb-release xdg-utils \
    unzip jq curl \
    --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

RUN ARCH=$(dpkg --print-architecture) \
    && if [ "$ARCH" = "amd64" ]; then \
        wget -q -O /tmp/google-chrome-stable_current_amd64.deb \
            https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
        && apt-get update \
        && apt-get install -y /tmp/google-chrome-stable_current_amd64.deb \
        && rm /tmp/google-chrome-stable_current_amd64.deb \
        && CHROME_VERSION=$(google-chrome --version | awk '{print $3}') \
        && CHROME_MAJOR=$(echo $CHROME_VERSION | cut -d. -f1) \
        && CHROMEDRIVER_VERSION=$(curl -s "https://googlechromelabs.github.io/chrome-for-testing/LATEST_RELEASE_$CHROME_MAJOR") \
        && wget -q -O /tmp/chromedriver-linux64.zip \
            "https://storage.googleapis.com/chrome-for-testing-public/$CHROMEDRIVER_VERSION/linux64/chromedriver-linux64.zip" \
        && unzip /tmp/chromedriver-linux64.zip -d /tmp/ \
        && mv /tmp/chromedriver-linux64/chromedriver /usr/local/bin/ \
        && chmod +x /usr/local/bin/chromedriver \
        && rm -f /tmp/chromedriver*.zip; \
    else \
        apt-get update \
        && apt-get install -y chromium chromium-driver \
        && ln -s /usr/bin/chromium /usr/bin/chromium-browser; \
    fi \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY . /app/

RUN chmod +x /app/start.sh

# fix for nodirver (running as root || not running sandbox)
RUN groupadd -r chrome && useradd -r -g chrome -m chrome
COPY --chown=chrome:chrome . /app
USER chrome

CMD ["/app/start.sh"]
