#!/bin/bash
#
# https://google.github.io/styleguide/shellguide.html

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

source "$SCRIPT_DIR/.env"
source "$SCRIPT_DIR/config.env"

source "$SCRIPT_DIR/proxypi/apt.sh"
source "$SCRIPT_DIR/proxypi/docker.sh"
source "$SCRIPT_DIR/proxypi/git.sh"
source "$SCRIPT_DIR/proxypi/ssh.sh"
source "$SCRIPT_DIR/proxypi/ui.sh"
source "$SCRIPT_DIR/proxypi/wireguard.sh"


LIGHTHOUSE_PRIVATE_KEY_PATH="$HOME/.ssh/id_proxy_access"

WIREGUARD_DEFAULT_PING_SAMPLE_SIZE="1"
DEFAULT_SSH_CONNECTION_PLUS_INSTRUCTIONS_TIMEOUT="16"
TCP_CONNECTION_TIMEOUT="8"


#######################################
#######################################

# should be rename aliases
declare -A FCT_MAP=(
    [apt-update]="apt::update"
    [apt-upgrade]="apt::upgrade"
    [connect]="ssh::connect"
    [container-restart]="docker::restart"
    [container-status]="docker::status"
    [deployment-tests]="docker::tests"
    [git-pull]="git::pull"
    [info]="ssh::info"
    [ram]="ssh::ram"
    [load-ssh]="ssh::copy_keys"
    [load-wireguard]="wireguard::load"
    [ping]="ssh::ping"
    [ping-wireguard]="wireguard::ping"
    [swarm-execute]="ssh::exec"
)

declare -A FCT_DESCR=(
    [apt-update]="Test if proxies' apt are up-to-date"
    [apt-upgrade]="Upgrades the proxies"
    [connect]="Connects the sheel to the proxy"
    [container-restart]="Restarts the containers broker and scraper depending on the node role"
    [container-status]="Check if the scraper container is running"
    [deployment-tests]="Starts the tests suite"
    [git-pull]="Upgrades the reference repository"
    [info]="same use as ping -w but properly done (1 is the lighthouse)"
    [ram]="get RAM and usage %"
    [load-ssh]="Retrieve ssh keys for easy access"
    [load-wireguard]="Add to the lighthouse the peer proxies keys"
    [ping]="Check connectivity and status of all proxies. -w for getting the info formatted for the web (list of dictionaries)."
    [ping-wireguard]="Check connectivity through Wireguard. -a for getting just the available ips address for the scraper component."
    [swarm-execute]="Run a command on ALL proxies. For script execution 'bash' and './' are not equivalent"
)

declare -A FCT_FLAGS=(
    [ping]="-w vpn_address"  # DEPRECATED! UNPROPER IMPLEMENTATION
    [ping-wireguard]="-a"
)


declare -A FCT_FLAGS_DESCR=(
    [ping-wireguard -a]="just print the available ip addresses. used by the scraper component"
)

declare -A FCT_ARGS=(
    [connect]="proxy_id"
    [container-restart]="node_id"
    [container-status]="node_id"
    [info]="node_id"
    [ram]="node_id"
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
            if [[ -z "$1" || "$1" -lt 2 || "$1" -gt 254 ]]; then
                echob "Error: the id specified is outside the range 2-254"
                echob "Example: $0 connect 2"
                help; exit $EXIT_CODE_WRONG_PARAMETERS
            fi

            proxy_id="$1"; shift

            "${FCT_MAP[$fct]}" "$proxy_id"
            ;;

        info)
            if [[ -z "$1" || "$1" -lt 1 || "$1" -gt 254 ]]; then
                echob "Error: the id specified is outside the range 1-254"
                echob "Example: $0 connect 2"
                help; exit $EXIT_CODE_WRONG_PARAMETERS
            fi

            proxy_id="$1"; shift

            "${FCT_MAP[$fct]}" "$proxy_id"
            ;;

        ram)
            if [[ -z "$1" || "$1" -lt 1 || "$1" -gt 254 ]]; then
                echob "Error: the id specified is outside the range 1-254"
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

        container-restart)
            if [[ -z "$1" || "$1" -lt 1 || "$1" -gt 254 ]]; then
                echob "Error: the id specified is outside the range 1-254"
                echob "Example: $0 restart 2"
                help; exit $EXIT_CODE_WRONG_PARAMETERS
            fi

            node_id="$1"; shift

            "${FCT_MAP[$fct]}" "$node_id"
            ;;

        container-status)
            if [[ -z "$1" || "$1" -lt 1 || "$1" -gt 254 ]]; then
                echob "Error: the id specified is outside the range 1-254"
                echob "Example: $0 status 2"
                help; exit $EXIT_CODE_WRONG_PARAMETERS
            fi

            node_id="$1"; shift

            "${FCT_MAP[$fct]}" "$node_id"
            ;;


    esac

done
