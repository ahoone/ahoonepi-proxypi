#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

source "$SCRIPT_DIR/ui.sh"
source "$SCRIPT_DIR/.env"
source "$SCRIPT_DIR/config.env"

set -euo pipefail

sudo apt-get install wireguard wireguard-tools

if sudo test -f /etc/wireguard/private.key; then
    echo Private key already exists!
else
    wg genkey | sudo tee /etc/wireguard/private.key
    sudo chmod 600 /etc/wireguard/private.key
fi

if sudo test -f /etc/wireguard/public.key; then
    echo Public key already exists!
else
    sudo cat /etc/wireguard/private.key | wg pubkey | sudo tee /etc/wireguard/public.key
fi

PRIVATE_KEY=$(sudo cat /etc/wireguard/private.key)
PUBLIC_KEY=$(sudo cat /etc/wireguard/public.key)

if [[ "$NODE_ROLE" = *"LIGHTHOUSE"* ]]; then

    echob "overwriting any loaded proxy, you should run ./proxypi load-wireguard"

    sudo bash -c "cat > /etc/wireguard/wg0.conf" << EOF
[Interface]
# Lighthouse server config
Address = 10.0.0.1/24
ListenPort = $LIGHTHOUSE_WIREGUARD_LISTEN_PORT
PrivateKey = $PRIVATE_KEY

# Enable IP forwarding
PostUp = sysctl -w net.ipv4.ip_forward=1
PostDown = sysctl -w net.ipv4.ip_forward=0
EOF

fi

if [[ "$NODE_ROLE" = *"PROXY"* ]]; then

    sudo bash -c "cat > /etc/wireguard/wg0.conf" << EOF
[Interface]
PrivateKey = ${PRIVATE_KEY}
Address = 10.0.0.$(printf "%02d" "$PROXY_ID")/24
ListenPort = ${LIGHTHOUSE_WIREGUARD_LISTEN_PORT}

[Peer]
# Lighthouse server
PublicKey = ${LIGHTHOUSE_WIREGUARD_PUBLIC_KEY}
Endpoint = ${LIGHTHOUSE_IP}:${LIGHTHOUSE_WIREGUARD_LISTEN_PORT}
AllowedIPs = 10.0.0.0/24
PersistentKeepalive = 25
EOF

fi

sudo systemctl enable wg-quick@wg0
sudo systemctl restart wg-quick@wg0
sudo wg show
