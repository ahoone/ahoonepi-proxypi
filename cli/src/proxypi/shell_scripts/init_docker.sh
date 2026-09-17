#!/bin/bash

#######################################
# https://docs.docker.com/engine/install/debian/
#######################################
# Uninstall all conflicting packages:
sudo apt remove -y $(dpkg --get-selections docker.io docker-compose docker-doc podman-docker containerd runc | cut -f1) || true

# Add Docker's official GPG key:
sudo apt update
sudo apt install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

# Add the repository to Apt sources:
sudo tee /etc/apt/sources.list.d/docker.sources <<EOF
Types: deb
URIs: https://download.docker.com/linux/debian
Suites: $(. /etc/os-release && echo "$VERSION_CODENAME")
Components: stable
Signed-By: /etc/apt/keyrings/docker.asc
EOF

sudo apt update

# Install the latest version:
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
#######################################

# Making docker usable without sudo
if ! getent group docker &>/dev/null; then
    sudo groupadd docker 2>&1
fi

if ! groups | grep docker &>/dev/null; then
    sudo usermod -aG docker "$(whoami)" 2>&1
fi

# Start docker on boot
sudo systemctl enable docker
