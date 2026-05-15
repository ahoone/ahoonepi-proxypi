#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

source "$SCRIPT_DIR/.env"

set -euo pipefail

: "${LIGHTHOUSE_SSH_PORT:?Environment variable LIGHTHOUSE_SSH_PORT not set}"
: "${LIGHTHOUSE_DUMMY_USER:?Environment variable LIGHTHOUSE_DUMMY_USER not set}"
: "${LIGHTHOUSE_IP:?Environment variable LIGHTHOUSE_IP not set}"
: "${PROXY_ID:?Environment variable PROXY_ID not set}"

ssh-keygen -t ed25519 -f ~/.ssh/id_lighthouse -N ""
ssh-copy-id -i ~/.ssh/id_lighthouse.pub -p ${LIGHTHOUSE_SSH_PORT} ${LIGHTHOUSE_DUMMY_USER}@${LIGHTHOUSE_IP}
ssh -i ~/.ssh/id_lighthouse -p ${LIGHTHOUSE_SSH_PORT} ${LIGHTHOUSE_DUMMY_USER}@${LIGHTHOUSE_IP} echo "Connection successful"

sudo bash -c "cat >/etc/systemd/system/reverse-ssh-tunnel.service" << EOF
[Unit]
Description=Reverse SSH Tunnel to Lighthouse
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$(whoami)
ExecStart=/usr/bin/ssh -N -T \
    -o ServerAliveInterval=60 \
    -o ServerAliveCountMax=3 \
    -o ExitOnForwardFailure=yes \
    -o StrictHostKeyChecking=accept-new \
    -i %h/.ssh/id_lighthouse \
    -p ${LIGHTHOUSE_SSH_PORT} \
    -R 22$(printf "%02d" "$PROXY_ID"):localhost:22 \
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
