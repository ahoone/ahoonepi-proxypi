#!/bin/bash
source ui.sh
source .env

set -euo pipefail


#######################################
#######################################


: "${NODE_ROLE:?Environment variable NODE_ROLE not set}"
echob "detected role: $NODE_ROLE"

declare -A REQUIRED_ENV_VAR=(
    [DDNS_UPKEEPER]="
        OVH_USER
        OVH_PASS
        OVH_HOST
    "
    [LIGHTHOUSE]="
        GIT_HOSTING_PROVIDER
        GIT_REPOSITORY
        GIT_BRANCH
        LIGHTHOUSE_DUMMY_USER
        HTTP_PORT_BROKER
        LIGHTHOUSE_WIREGUARD_LISTEN_PORT
    "
    [PROXY]="
        LIGHTHOUSE_WIREGUARD_PUBLIC_KEY
        LIGHTHOUSE_WIREGUARD_LISTEN_PORT
        LIGHTHOUSE_DUMMY_USER
        LIGHTHOUSE_SSH_PORT
        LIGHTHOUSE_IP
        PROXY_ID
    "
    [SCRAPER]="
        HTTP_PORT_SCRAPER
    "
)

bool_missing_required_env_var=false
for role in "${!REQUIRED_ENV_VAR[@]}"; do
    if [[ "$NODE_ROLE" = *"$role"* ]]; then

        for required_env_var_for_role in ${REQUIRED_ENV_VAR[$role]}; do
            if [[ -z "${!required_env_var_for_role}" ]]; then
                echo "Environment variable $required_env_var_for_role not set"
                bool_missing_required_env_var=true
            fi
        done

    fi
done

if "$bool_missing_required_env_var"; then
    exit
fi

if [[ "$NODE_ROLE" = *"LIGHTHOUSE"* ]] || [[ "$NODE_ROLE" = *"PROXY"* ]]; then
    echob "duck off, incompatible roles of proxy and lighthouse for now"
fi


#######################################
#######################################


echob "upgrading..."
sudo apt-get update
sudo apt-get upgrade -y

echob "initializing docker..."
./init_docker.sh

echob "initializing wireguard..."
./init_wireguard.sh


#######################################
#######################################


if [[ "$NODE_ROLE" = *"LIGHTHOUSE"* ]]; then

    echob "LIGHTHOUSE:"

    echob "installing packages..."
    xargs sudo apt-get install -y < aptfile

    echob "cleanup..."
    sudo apt-get autoremove -y

    echob "proxypi socket initializing for broker usage..."
    ./proxypi_socket_init.sh

    echob "creating proxypi host user..."
    if getent passwd | grep -q "^$LIGHTHOUSE_DUMMY_USER:"; then
        echo "$LIGHTHOUSE_DUMMY_USER user already exists!"
    else 
        # Needs a home directory. SSH public keys from proxies are stored in '~/.ssh'.
        sudo adduser "$LIGHTHOUSE_DUMMY_USER"
    fi

    echob "creating $(pwd)/.ssh folder..."
    mkdir -p .ssh
    if ls .ssh | grep -q "id_proxy_access"; then
        echo "ssh public key for proxies already exists."
    else 
        ssh-keygen -t ed25519 -f ~/.ssh/id_proxy_access -N ""
        echob "Created public ssh key for the proxies at '$(pwd)/.ssh/id_proxy_access.pub'." 
    fi | draw_box

    echob "starting Nginx Proxy Manager docker container..."
    echo -e $(docker compose -f nginx-proxy-manager/docker-compose.yml up -d 2>&1) | draw_box && echob "✓ NPM running." || echob "✗ NPM failed running." 

fi


#######################################
#######################################


if [[ "$NODE_ROLE" = *"DDNS_UPKEEPER"* ]]; then

    echob "DDNS_UPKEEPER:"

    echob "initializing ddns crontab job..."
    ./ddns/init.sh

fi


#######################################
#######################################


if [[ "$NODE_ROLE" = *"PROXY"* ]]; then
    
    echob "PROXY:"

    echob "initializing ssh reverse tunnel..."
    ./init_ssh.sh

fi
