#!/bin/bash
#
# https://google.github.io/styleguide/shellguide.html

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

source "$SCRIPT_DIR/ui.sh"
source "$SCRIPT_DIR/.env"
source "$SCRIPT_DIR/config.env"

LIGHTHOUSE_PRIVATE_KEY_PATH="$HOME/.ssh/id_proxy_access"

WIREGUARD_DEFAULT_PING_SAMPLE_SIZE="1"
DEFAULT_SSH_CONNECTION_PLUS_INSTRUCTIONS_TIMEOUT="16"
TCP_CONNECTION_TIMEOUT="8"


#######################################
#######################################


declare -A FCT_MAP=(
    [apt-update]="apt::update"
    [apt-upgrade]="apt::upgrade"
    [connect]="ssh::connect"
    [git-pull]="git::pull"
    [info]="ssh::info"
    [ram]="ssh::ram"
    [load-ssh]="ssh::copy_keys"
    [load-wireguard]="wireguard::load"
    [ping]="ssh::ping"
    [ping-wireguard]="wireguard::ping"
    [restart]="docker::restart"
    [swarm-execute]="ssh::exec"
)

declare -A FCT_DESCR=(
    [apt-update]="Test if proxies' apt are up-to-date"
    [apt-upgrade]="Upgrades the proxies"
    [connect]="Connects the sheel to the proxy"
    [git-pull]="Upgrades the reference repository"
    [info]="same use as ping -w but properly done (1 is the lighthouse)"
    [ram]="get RAM and usage %"
    [load-ssh]="Retrieve ssh keys for easy access"
    [load-wireguard]="Add to the lighthouse the peer proxies keys"
    [ping]="Check connectivity and status of all proxies. -w for getting the info formatted for the web (list of dictionaries)."
    [ping-wireguard]="Check connectivity through Wireguard. -a for getting just the available ips address for the scraper component."
    [restart]="Restarts the containers broker and scraper depending on the node role"
    [swarm-execute]="Run a command on ALL proxies. For script execution 'bash' and './' are not equivalent"
)

declare -A FCT_FLAGS=(
    [ping]="-w vpn_address"  # DEPRECATED! UNPROPER IMPLEMENTATION
    [ping-wireguard]="-a"
)

declare -A FCT_ARGS=(
    [connect]="proxy_id"
    [info]="node_id"
    [ram]="node_id"
    [restart]="node_id"
    [swarm-execute]="timeout command"
)


EXIT_CODE_MISSING_ARGUMENT=1
EXIT_CODE_UNKNOWN_FUNCTION=2
EXIT_CODE_WRONG_PARAMETERS=3
EXIT_CODE_NO_FLAG_FUNCTION=4
EXIT_CODE_UNKNOWN_FLAG=5
EXIT_CODE_NOT_IMPLEMENTED=6


# TODO (ahoone): HERE WE SHOULD VERIFY THE ROLES OF THE PI (SCRAPER) AND IF THE REMOTE CONTAINER IS RUNNING
FLAG_PING_INFO_FROM_VPN_ADDRESS=false
FLAG_PING_WIREGUARD_PRINT_AVAILABLE=false
FLAG_PARAMETER_VPN_ADDRESS=""


#######################################
#######################################


#######################################
# loop to format the flags
# Arguments:
#   $1: the docstring of flags
# Outputs:
#   String to stdout
# Returns:
#   0 on success
#######################################
fmt_flags() {
    local fct_flags=$1
    local fmt_fct_flags=""

    if [[ -n "$fct_flags" ]]; then
        current=""
        for token in $fct_flags; do
            if [[ "$token" == -* ]]; then
                [[ -n "$current" ]] && fmt_fct_flags+="$current] "
                current="[$token"
            else
                current+=" <$token>"
            fi
        done
        [[ -n "$current" ]] && fmt_fct_flags+="$current]"
        fmt_fct_flags="${fmt_fct_flags% }"  # trim trailing space
    fi

    echo "$fmt_fct_flags"
}


#######################################
# Halp
# Outputs:
#   Help to stdout
# Returns:
#   0 on success
#######################################
help() {
    local column_size=(48 128)

    local header="$(basename "$0") - ProxyPi Management Tool"
    echob $header
    echo "$(repeat_string '=' $(len $header))"

    mapfile -t sorted < <(printf '%s\n' "${!FCT_MAP[@]}" | sort)

    local fct_descr fct_args_descr fmt_fct_args_descr fct_call entry
    for fct in "${sorted[@]}"; do

        fct_flags="${FCT_FLAGS[$fct]}"
        fct_args="${FCT_ARGS[$fct]}"

        fmt_fct_flags=$(fmt_flags "$fct_flags")
        fmt_fct_args=$([[ -n "$fct_args" ]] && echo "<${fct_args// /> <}>")

        # TODO (ahoone): here a double space is printed if there are args descr but no flags
        fct_call="$(echob "\n\t$(echob $fct) $fmt_fct_flags $fmt_fct_args")"
        fct_descr="${FCT_DESCR[$fct]}"
        entry=("$fct_call" "$fct_descr")

        draw_tabular_row column_size entry TABULAR_EMPTY_STYLE
    done
}


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
_proxypi_listen_ssh() {
    if [[ "$WIREGUARD_CIDR_PREFIX" -eq 24 ]]; then
        NETWORK_SIZE=255
    else
        return $EXIT_CODE_NOT_IMPLEMENTED
    fi
    
    START=$SSH_NETWORK_BASE
    END=$((SSH_NETWORK_BASE + NETWORK_SIZE - 1))
    
    ports=$(netstat -an | grep '0.0.0.0' | awk -v start=2202 -v end=2456 '{split($4, buf, ":"); port=buf[2]; if (port>=start && port<=end) print port}')
    
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
_proxypi_execute_command() {
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
    for port in $(_proxypi_listen_ssh); do
        (
            # if [[ "$FLAG_PING_INFO_FROM_VPN_ADDRESS" == "true" && "$port" != *"$vpn_address" ]]; then
            #   continue
            # fi

            ssh_start_time=$(date +%s%3N)
            _proxypi_execute_command "$port" "whoami" &>/dev/null
            ssh_end_time=$(date +%s%3N)
            
            ssh_result=$(_proxypi_execute_command "$port" "$instructions")

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
    for port in $(_proxypi_listen_ssh); do
        (
            ssh_result=$(_proxypi_execute_command "$port" "$instructions" "$command_timeout")
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
    for port in $(_proxypi_listen_ssh); do
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
# Check APT packages are up to date
# Outputs:
#   Table to stdout
# Returns:
#   0 on success, non-zero on error
#######################################
apt::update() {
    local column_name=("HOSTNAME" "PORT" "UP TO DATE")
    local column_size=(24 8 24)
    draw_tabular_header column_size column_name

    #--------------------------------------
    local hostname=$(hostname)
    local apt_status=$(sudo apt-get update >/dev/null && echo "✓ Up to date." || echo "✗ Update.s available.")
    local label="$hostname $(echob '(lighthouse)')"
    local entry=("$label" "" "${apt_status}")
    draw_tabular_row column_size entry
    #--------------------------------------

    local instructions='echo $(hostname) $(sudo apt-get update >/dev/null && echo "✓ Up to date." || echo "✗ Update.s available.")'

    local ssh_result proxypi_hostname
    for port in $(_proxypi_listen_ssh); do
        (
            ssh_result=$(_proxypi_execute_command "$port" "$instructions")
            read proxypi_hostname apt_status <<< "$ssh_result"

            entry=("$proxypi_hostname" "$port" "$apt_status")
            draw_tabular_row column_size entry
        ) &
    done
    wait
}


#######################################
# Upgrades APT packages (excluding the lighthouse)
# Outputs:
#   Table to stdout
# Returns:
#   0 on success, non-zero on error
#######################################
apt::upgrade() {
    echob "Does not upgrade the lighthouse." >&2
    local column_name=("HOSTNAME" "PORT" "UP TO DATE")
    local column_size=(24 8 24)
    draw_tabular_header column_size column_name

    local instructions='echo $(hostname) $(sudo -n apt-get upgrade -y >/dev/null && echo "✓ Up to date." || echo "✗ Failed.")'

    local ssh_result proxypi_hostname apt_status entry
    for port in $(_proxypi_listen_ssh); do
        (
            ssh_result=$(_proxypi_execute_command "$port" "$instructions")
            read proxypi_hostname apt_status <<< "$ssh_result"

            entry=("$proxypi_hostname" "$port" "$apt_status")
            draw_tabular_row column_size entry
        ) &
    done
    wait
}


#######################################
# Upgrades Git repository
# Globals:
#   GIT_HOSTING_PROVIDER
#   GIT_REPOSITORY
#   GIT_BRANCH
# Outputs:
#   Table to stdout
# Returns:
#   0 on success, non-zero on error
#######################################
git::pull() {
    echob "Will use ${GIT_HOSTING_PROVIDER}/${GIT_REPOSITORY} (branch ${GIT_BRANCH}) as the target." >&2

    local column_name=("HOSTNAME" "PORT" "ORIGIN" "HEAD" "UP TO DATE")
    local column_size=(24 8 54 64 30)
    draw_tabular_header column_size column_name

    # I did not manage to correctly parse the echo after the hard reset,
    # so I just ran the command twice redirecting the prints to bin.
    local instructions='
        printf "%b|%b|%b|%b" \
        "$(hostname)" \
        "$(git -C GIT_REPOSITORY remote set-url origin GIT_TARGET && git -C GIT_REPOSITORY remote -v | awk "/fetch/ {print \$2; exit}")" \
        "$(git -C GIT_REPOSITORY fetch >/dev/null && git -C GIT_REPOSITORY reset --hard origin/GIT_BRANCH)" \
        "$(git -C GIT_REPOSITORY reset --hard origin/GIT_BRANCH >/dev/null && echo ✓ Up\ to\ date. || echo ✗ Failed.)"
    '
    instructions="${instructions//GIT_BRANCH/${GIT_BRANCH}}"
    instructions="${instructions//GIT_REPOSITORY/${GIT_REPOSITORY}}"
    instructions="${instructions//GIT_TARGET/${GIT_HOSTING_PROVIDER}/${GIT_REPOSITORY}}"

    local ssh_result proxypi_hostname origin commit_head repo_status entry
    for port in $(_proxypi_listen_ssh); do
        (
            ssh_result=$(_proxypi_execute_command "$port" "$instructions")

            IFS='|' read proxypi_hostname origin commit_head repo_status <<< "$ssh_result"

            entry=("$proxypi_hostname" "$port" "$origin" "$commit_head" "$repo_status")
            draw_tabular_row column_size entry
        ) &
    done
    wait
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

    if ! [[ "$(_proxypi_listen_ssh)" =~ "$port" ]]; then
        return 1
    fi

#    if ! [[ "$(./proxypi.sh ping-wireguard -a)" =~ "10.0.0.$proxy_id" ]]; then
#        return 2
#    fi

    local instructions="echo \
        \$(hostname) \
        \$(curl ifconfig.me 2>/dev/null || echo 'N/A')
    "

    ssh_result=$(_proxypi_execute_command "$port" "$instructions")
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

    if ! [[ "$(_proxypi_listen_ssh)" =~ "$port" ]]; then
        return 1
    fi

    if ! [[ "$(./proxypi.sh ping-wireguard -a)" =~ "10.0.0.$proxy_id" ]]; then
        return 2
    fi

    local instructions="echo \
        \$(free -h | awk '/^Mem:/{print \$2}') \
        \$(free | awk '/^Mem:/{printf \"\%.0f%%\", \$3/\$2*100}')
    "

    ssh_result=$(_proxypi_execute_command "$port" "$instructions")
    read ram ram_usage <<< "$ssh_result"
    echo "{\"ram_specs\": \"$ram\", \"ram_usage\": \"$ram_usage\"}"
}


#######################################
# Ping proxys through VPN
# Globals:
#   WIREGUARD_NETWORK_PREFIX
#   FLAG_PING_WIREGUARD_PRINT_AVAILABLE
# Arguments:
#   $1: ping sample size
# Outputs:
#   Updates to stdout
# Returns:
#   0 on success
#   1 on failing the peer update
#######################################
wireguard::ping() {
    local wireguard_ping_sample_size="${1:-$WIREGUARD_DEFAULT_PING_SAMPLE_SIZE}"

    if ! "$FLAG_PING_WIREGUARD_PRINT_AVAILABLE"; then
        local column_name=("HOSTNAME" "IP" "UPSIDE LATENCY (ms)" "UPSIDE LOSS" "DOWNSIDE LATENCY (ms)" "DOWNSIDE LOSS")
        local column_size=(24 16 24 16 24 16)
        draw_tabular_header column_size column_name
    else
        echo "$WIREGUARD_NETWORK_PREFIX.1"
    fi

    local instructions='echo $(hostname) echo $PROXY_ID $(ping -c PING_COUNT PING_TARGET | awk '\''/packet loss/{loss=$6} /(rtt|round-trip)/{split($4,a,"/");avg=a[2]} END{print avg,loss}'\'')'
    instructions="${instructions//PING_COUNT/${wireguard_ping_sample_size}}"
    instructions="${instructions//PING_TARGET/${WIREGUARD_NETWORK_PREFIX}.1}"
    


    local ssh_result target proxypi_hostname proxypi_id upside_latency upside_loss downside_result downside_latency downside_loss entry
    for port in $(_proxypi_listen_ssh); do
        (
            ssh_result=$(_proxypi_execute_command "$port" "$instructions")
            read proxypi_hostname proxypi_id upside_latency upside_loss <<< "$ssh_result"
            target="${WIREGUARD_NETWORK_PREFIX}.${proxypi_id}"

            # If no packets where exchanged (ie proxy is not connected)
            if [[ "$upside_latency" == *"100%"* ]]; then
                proxypi_hostname=$(echob $proxypi_hostname)
                target=$(echob "${target} (?!)")
                upside_latency=$(echob -)
                upside_loss=$(echob 100%)
                downside_latency=$(echob -)
                downside_loss=$(echob -)
            else
                downside_result=$(ping -c "${wireguard_ping_sample_size}" "${target}" | awk '/packet loss/{loss=$6} /(rtt|round-trip)/{split($4,a,"/");avg=a[2]} END{print avg,loss}')
                read downside_latency downside_loss <<< "$downside_result"
            fi

            if ! $FLAG_PING_WIREGUARD_PRINT_AVAILABLE; then
                entry=("$proxypi_hostname" "${target}" "$upside_latency" "$upside_loss" "$downside_latency" "$downside_loss")
                draw_tabular_row column_size entry
            fi

            if "$FLAG_PING_WIREGUARD_PRINT_AVAILABLE" && [[ "$upside_loss" == "0%" ]] && [[ "$downside_loss" == "0%" ]]; then
                echo "$target"
            fi
        ) &
    done
    wait
}


#######################################
# Establish VPN with all proxy Pis
# Globals:
#   WIREGUARD_NETWORK_PREFIX
# Outputs:
#   Updates to stdout
# Returns:
#   0 on success
#   1 on failing the peer update
#######################################
wireguard::load() {
    local instructions="echo \
        \$(hostname) \
        \$(echo \$PROXY_ID) \
        \$(sudo wg show wg0 public-key)"

    local ssh_result proxypi_hostname proxypi_id proxypi_public_key

    # TODO (ahoone): No parallelization // RACE CONDITION ON WG SET WG0 PEER AND SAVE

    for port in $(_proxypi_listen_ssh); do
        ssh_result=$(_proxypi_execute_command "$port" "$instructions")
        read proxypi_hostname proxypi_id proxypi_public_key <<< "$ssh_result"

        if [ -z "$proxypi_public_key" ]; then
            echob "ProxyPi $proxypi_hostname have not been initialized (no public key)"
        else
            sudo wg set wg0 peer ${proxypi_public_key} allowed-ips ${WIREGUARD_NETWORK_PREFIX}.${proxypi_id}/32 || return 1
            sudo wg-quick save wg0 2>/dev/null
        fi
    done

    sudo wg show | draw_box
}


#######################################
# Restarts the containers
# Arguments:
#   $1: node_id
# Returns:
#   0 on success
#######################################
docker::restart() {
    local node_id=$1
    
    if [[ "$node_id" == "1" ]]; then
        cd "$SCRIPT_DIR"
        docker compose -f scraper/docker-compose.yml down
        docker compose -f scraper/docker-compose.yml --env-file .env --env-file config.env up --build -d
        docker compose -f broker/docker-compose.yml down
        docker compose -f broker/docker-compose.yml --env-file .env --env-file config.env up --build -d
    else
        echob "NOT IMPLEMENTED FOR OTHER THAN NODE_ID=1"
        return $EXIT_CODE_NOT_IMPLEMENTED
    fi
    # TODO (ahoone): implementing for the proxies
}


#######################################
#######################################


# no fucking idea if this working to stop the execution when sourced
if [[ "${BASH_SOURCE[0]}" != "${0}" ]]; then
    return
fi


if [[ $# -eq 0 ]]; then
    echob "Missing argument."
    help; exit $EXIT_CODE_MISSING_ARGUMENT
fi


while [[ $# -gt 0 ]]; do

    fct="$1"; shift

    if [[ -z "${FCT_MAP[$fct]}" ]]; then
        echob "Unknown function: '$fct'"
        help; exit $EXIT_CODE_UNKNOWN_FUNCTION
    fi

    # flags must start with a dash
    while [[ $1 == "-"* ]]; do
        if [[ -z "${FCT_FLAGS[$fct]}" ]]; then
            echob "Function '$fct' has no flag"
            help; exit $EXIT_CODE_NO_FLAG_FUNCTION
        fi

        flag="$1"; shift
        
        if [[ "${FCT_FLAGS[$fct]}" != *"$flag"* ]]; then
            echob "Function '$fct' has no flag '$flag'"
            help; exit $EXIT_CODE_UNKNOWN_FLAG
        fi
        
        case "$fct" in
            ping)
                if [[ $flag == "-w" ]]; then
                    FLAG_PING_INFO_FROM_VPN_ADDRESS=true;
                    FLAG_PARAMETER_VPN_ADDRESS=$1; shift
                fi
                ;;
            ping-wireguard)
                if [[ $flag == "-a" ]]; then FLAG_PING_WIREGUARD_PRINT_AVAILABLE=true; fi
                ;;
        esac
    done

    # if no arguments, you launch the fct
    if [[ -z "${FCT_ARGS[$fct]}" ]]; then
        "${FCT_MAP[$fct]}"; continue
    fi

    case "$fct" in
        connect)
            if [[ -z "$1" || ! "$1" =~ ^([2-9]|[1-9][0-9])$ ]]; then
                echob "Error: the id specified is outside the range 2-99"
                echob "Example: $0 connect 2"
                help; exit $EXIT_CODE_WRONG_PARAMETERS
            fi

            proxy_id="$1"; shift

            "${FCT_MAP[$fct]}" "$proxy_id"
            ;;

        info)
            if [[ -z "$1" || ! "$1" =~ ^([1-9]|[1-9][0-9])$ ]]; then
                echob "Error: the id specified is outside the range 1-99"
                echob "Example: $0 connect 2"
                help; exit $EXIT_CODE_WRONG_PARAMETERS
            fi

            proxy_id="$1"; shift

            "${FCT_MAP[$fct]}" "$proxy_id"
            ;;

        ram)
            if [[ -z "$1" || ! "$1" =~ ^([1-9]|[1-9][0-9])$ ]]; then
                echob "Error: the id specified is outside the range 1-99"
                echob "Example: $0 connect 2"
                help; exit $EXIT_CODE_WRONG_PARAMETERS
            fi

            proxy_id="$1"; shift

            "${FCT_MAP[$fct]}" "$proxy_id"
            ;;

        swarm-execute)

            if [[ -z "$1" || ! "$1" =~ ^[0-9]+$ ]]; then
                echob "Error: swarm-execute requires timeout as first argument."
                echob "Usage: $0 swarm-execute <timeout_seconds> <command> [args...]"
                echob "Example: $0 swarm-execute 30 apt update"
                echob "Example: $0 swarm-execute 600 bash init_docker.sh"
                help; exit $EXIT_CODE_WRONG_PARAMETERS
            fi
            
            swarm_timeout="$1"; shift

            if [[ $# -eq 0 ]]; then
                echob "Error: swarm-execute requires a command after timeout."
                echob "Usage: $0 swarm-execute <timeout_seconds> <command> [args...]"
                echob "Example: $0 swarm-execute 30 apt update"
                help; exit $EXIT_CODE_WRONG_PARAMETERS
            fi
            
            "${FCT_MAP[$fct]}" "$swarm_timeout" "$*"; shift $#
            ;;

        restart)
            if [[ -z "$1" || ! "$1" =~ ^([1-9]|[1-9][0-9])$ ]]; then
                echob "Error: the id specified is outside the range 1-99"
                echob "Example: $0 restart 2"
                help; exit $EXIT_CODE_WRONG_PARAMETERS
            fi

            node_id="$1"; shift

            "${FCT_MAP[$fct]}" "$node_id"
            ;;

    esac

done
