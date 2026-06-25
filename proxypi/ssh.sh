#######################################
# Examines open ports in the specified range
# Globals:
#   NETWORK_SIZE
#   SSH_NETWORK_BASE
#   WIREGUARD_CIDR_PREFIX
# Outputs:
#   Ports to stdout
# Returns:
#   0 on success
#   1 on no proxies found
#######################################
ssh::listen() {
    if [[ "$WIREGUARD_CIDR_PREFIX" -eq 24 ]]; then
        NETWORK_SIZE=253
    else
        return $EXIT_CODE_NOT_IMPLEMENTED
    fi

    local start=$SSH_NETWORK_BASE
    local end=$((SSH_NETWORK_BASE + NETWORK_SIZE - 1))

    ports=$(netstat -an | grep '0.0.0.0' | awk -v start=$start -v end=$end '{split($4, buf, ":"); port=buf[2]; if (port>=start && port<=end) print port}')

    if [ -z "$ports" ]; then
        echob "No proxies found." >&2
        echo ""
        return 1
    else
        echo $ports
    fi
}

#######################################
# Execute command on remote proxy Pi
# Globals:
#   DEFAULT_SSH_CONNECTION_PLUS_INSTRUCTIONS_TIMEOUT
#   LIGHTHOUSE_PRIVATE_KEY_PATH
#   TCP_CONNECTION_TIMEOUT
#   PROXYPI_USER
# Arguments:
#   $1: Port number of reverse SSH tunnel
#   $2: Command string to execute
#   $3: Specific timeout if given
# Outputs:
#   Command output to stdout
# Returns:
#   0 on success, non-zero on error
#######################################
ssh::execute_command() {
    local port=$1
    local instructions=$2
    local command_timeout=${3:-$DEFAULT_SSH_CONNECTION_PLUS_INSTRUCTIONS_TIMEOUT}

    timeout "$command_timeout" \
        ssh -i "$LIGHTHOUSE_PRIVATE_KEY_PATH" \
        -o StrictHostKeyChecking=no \
        -o ConnectTimeout="$TCP_CONNECTION_TIMEOUT" \
        -p "$port" \
        "$PROXYPI_USER"@localhost \
        "$instructions" 2>/dev/null
}

#######################################
# Check connectivity to all proxy Pis
# Globals :
#   FLAG_PING_INFO_FROM_VPN_ADDRESS
#   FLAG_PARAMETER_VPN_ADDRESS
# Outputs:
#   Formatted table to stdout
# Returns:
#   0 on success
#######################################
ssh::ping() {

    local column_name=("HOSTNAME" "PROXY ID" "PORT" "IPv6 ADDRESS" "SSH (RTT) (ms)" "INTERNET (ms)")
    if ! "$FLAG_PING_INFO_FROM_VPN_ADDRESS"; then
        local column_size=(24 8 8 45 16 16)
        draw_tabular_header column_size column_name
    else
        local vpn_address=$FLAG_PARAMETER_VPN_ADDRESS
        echob "Deprecated -w flag"
    fi

    #--------------------------------------
    local hostname=$(hostname)
    local internet_start_time=$(date +%s%3N)
    local ipv6=$(curl -s ifconfig.me)
    local internet_end_time=$(date +%s%3N)
    local internet_latency=$((internet_end_time - internet_start_time))

    local label_hostname="$hostname $(echob '(lighthouse)')"
    local label_proxy_id="$(echob '1')"
    local entry=("$label_hostname" "$label_proxy_id" "" "$ipv6" "" "${internet_latency}")
    if ! "$FLAG_PING_INFO_FROM_VPN_ADDRESS"; then
        draw_tabular_row column_size entry
    elif [[ "$vpn_address" == "$WIREGUARD_NETWORK_PREFIX.1" ]]; then
        echo "${entry[@]}"
    fi


    #--------------------------------------

    local instructions="echo \
        \$(hostname) \
        \$(source ahoonepi-proxypi/.env && echo \$PROXY_ID) \
        \$(date +%s%3N) \
        \$(curl ifconfig.me 2>/dev/null || echo 'N/A') \
        \$(date +%s%3N)"

    local ssh_start_time ssh_result ssh_end_time
    for port in $(ssh::listen); do
        (
            # if [[ "$FLAG_PING_INFO_FROM_VPN_ADDRESS" == "true" && "$port" != *"$vpn_address" ]]; then
            #   continue
            # fi

            ssh_start_time=$(date +%s%3N)
            ssh::execute_command "$port" "whoami" &>/dev/null
            ssh_end_time=$(date +%s%3N)

            ssh_result=$(ssh::execute_command "$port" "$instructions")

#            if [ -z "$ssh_result" ]; then
#                if ! "$FLAG_PING_INFO_FROM_VPN_ADDRESS"; then
#                    entry=("---" "$(echob $port)" "---" "$(echob UNREACHABLE)" "---")
#                    draw_tabular_row column_size entry
#                else
#                    continue
#                fi
#            fi

            read hostname proxy_id internet_start_time ipv6 internet_end_time <<< "$ssh_result"

            ssh_latency=$((ssh_end_time - ssh_start_time))
            internet_latency=$((internet_end_time - internet_start_time))

            entry=("$hostname" "$proxy_id" "$port" "$ipv6" "$ssh_latency" "$internet_latency")
            if ! "$FLAG_PING_INFO_FROM_VPN_ADDRESS"; then
                draw_tabular_row column_size entry
            else
                echo "${entry[@]}"
            fi
        ) &
    done
    wait
}


#######################################
# Execute command on ALL proxy Pi
# Arguments:
#   $1: timeout in seconds (required)
#   $2: command
# Outputs:
#   Success table on stdout
# Returns:
#   0 on success, non-zero on error
#######################################
ssh::exec() {
    local command_timeout=$1
    local command=$2

    local column_name=("HOSTNAME" "PORT" "COMMAND STATUS" "COMMAND LATENCY (ms)")
    local column_size=(24 8 18 24)
    draw_tabular_header column_size column_name

    local instructions='
        printf "%b|%b|%b|%b" \
        "$(hostname)" \
        "$(date +%s%3N)" \
        "$(COMMAND >/dev/null && echo ✓ Success. || echo ✗ Failed.)" \
        "$(date +%s%3N)"
    '
    instructions="${instructions//COMMAND/${command}}"

    local ssh_result start_time end_time proxypi_hostname command_status entry
    for port in $(ssh::listen); do
        (
            ssh_result=$(ssh::execute_command "$port" "$instructions" "$command_timeout")
            IFS='|' read hostname start_time command_status end_time <<< "$ssh_result"

            command_latency=$((end_time - start_time))

            entry=("$hostname" "$port" "$command_status" "$command_latency")
            draw_tabular_row column_size entry
        ) &
    done
    wait
}


#######################################
# Copy the ssh keys
# Returns:
#   0 on success, non-zero on error
#######################################
ssh::copy_keys() {
    for port in $(ssh::listen); do
        local proxy_id=$((port - SSH_NETWORK_BASE + 2))
        echob "for $port (proxy id: $proxy_id)"
        ssh-copy-id -i "$LIGHTHOUSE_PRIVATE_KEY_PATH".pub -p "$port" "$PROXYPI_USER"@localhost
    done
}


#######################################
# Connect to a Proxy
# Arguments:
#   $1: proxy id
# Outputs:
#   Success table on stdout
# Returns:
#   0 on success, non-zero on error
#######################################
ssh::connect() {
    local proxy_id=$1
    local port=$((SSH_NETWORK_BASE + proxy_id - 2))

    ssh -i "$LIGHTHOUSE_PRIVATE_KEY_PATH" -p "$port" "$PROXYPI_USER"@localhost
}

#######################################
# Get the info for the ScraperImage
# Arguments:
#   $1: proxy id
# Outputs:
#   Dictionary to stdout
# Returns:
#   0 on success
#   1 on unknown port
#   2 on unresponsive ip
#######################################
ssh::info() {
    local proxy_id=$1
    local port=$((SSH_NETWORK_BASE + proxy_id - 2))

    if [[ "$proxy_id" == "1" ]]; then
        echo "{\"hostname\": \"$(hostname)\", \"port\": \"$port\", \"ipv6\": \"$(curl ifconfig.me 2>/dev/null || echo 'N/A')\"}"
        return
    fi

    if ! [[ "$(ssh::listen)" =~ "$port" ]]; then
        return 1
    fi

#    if ! [[ "$(./proxypi.sh ping-wireguard -a)" =~ "10.0.0.$proxy_id" ]]; then
#        return 2
#    fi

    local instructions="echo \
        \$(hostname) \
        \$(curl ifconfig.me 2>/dev/null || echo 'N/A')
    "

    ssh_result=$(ssh::execute_command "$port" "$instructions")
    read node_hostname node_ipv6 <<< "$ssh_result"
    echo "{\"hostname\": \"$node_hostname\", \"port\": \"$port\", \"ipv6\": \"$node_ipv6\"}"
}


#######################################
# Get the RAM usage
# Arguments:
#   $1: proxy id
# Outputs:
#   Dictionary to stdout
# Returns:
#   0 on success
#   1 on unknown port
#   2 on unresponsive ip
#######################################
ssh::ram() {
    local proxy_id=$1
    local port=$((SSH_NETWORK_BASE + proxy_id - 2))

    if [[ "$proxy_id" == "1" ]]; then
        echo "{\"ram_specs\": \"$(free -h | awk '/^Mem:/{print $2}')\", \"ram_usage\": \"$(free | awk '/^Mem:/{printf "%.0f%%", $3/$2*100}')\"}"
        return
    fi

    if ! [[ "$(ssh::listen)" =~ "$port" ]]; then
        return 1
    fi

    if ! [[ "$(./proxypi.sh ping-wireguard -a)" =~ "10.0.0.$proxy_id" ]]; then
        return 2
    fi

    local instructions="echo \
        \$(free -h | awk '/^Mem:/{print \$2}') \
        \$(free | awk '/^Mem:/{printf \"\%.0f%%\", \$3/\$2*100}')
    "

    ssh_result=$(ssh::execute_command "$port" "$instructions")
    read ram ram_usage <<< "$ssh_result"
    echo "{\"ram_specs\": \"$ram\", \"ram_usage\": \"$ram_usage\"}"
}
