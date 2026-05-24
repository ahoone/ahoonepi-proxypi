#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

source "$SCRIPT_DIR/.env"
source "$SCRIPT_DIR/config.env"

set -euo pipefail

: "${LIGHTHOUSE_SSH_PORT:?Environment variable LIGHTHOUSE_SSH_PORT not set}"
: "${LIGHTHOUSE_DUMMY_USER:?Environment variable LIGHTHOUSE_DUMMY_USER not set}"
: "${LIGHTHOUSE_IP:?Environment variable LIGHTHOUSE_IP not set}"
: "${PROXY_ID:?Environment variable PROXY_ID not set}"
: "${SSH_NETWORK_BASE:?Environment variable SSH_NETWORK_BASE not set}"

local port=$((SSH_NETWORK_BASE + PROXY_ID - 2))

ssh-keygen -t ed25519 -f ~/.ssh/id_lighthouse -N ""
ssh-copy-id -i ~/.ssh/id_lighthouse.pub -p ${LIGHTHOUSE_SSH_PORT} ${LIGHTHOUSE_DUMMY_USER}@${LIGHTHOUSE_IP}
ssh -i ~/.ssh/id_lighthouse -p ${LIGHTHOUSE_SSH_PORT} ${LIGHTHOUSE_DUMMY_USER}@${LIGHTHOUSE_IP} echo "Connection successful"

CURRENT_USER=$(whoami)
CURRENT_HOME=$HOME

sudo bash -c "cat >/etc/systemd/system/reverse-ssh-tunnel.service" << EOF
[Unit]
Description=Reverse SSH Tunnel to Lighthouse
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${CURRENT_USER}
ExecStart=/usr/bin/ssh -N -T \
    -o ServerAliveInterval=60 \
    -o ServerAliveCountMax=3 \
    -o ExitOnForwardFailure=yes \
    -o StrictHostKeyChecking=accept-new \
    -i ${CURRENT_HOME}/.ssh/id_lighthouse \
    -p ${LIGHTHOUSE_SSH_PORT} \
    -R"${port}:localhost:22 \
    ${LIGHTHOUSE_DUMMY_USER}@${LIGHTHOUSE_IP}
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable reverse-ssh-tunnel.service
sudo systemctl start reverse-ssh-tunnel.service
sudo systemctl status reverse-ssh-tunnel.service
