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

    local instructions='echo $(hostname) $(ping -c PING_COUNT PING_TARGET | awk '\''/packet loss/{loss=$6} /(rtt|round-trip)/{split($4,a,"/");avg=a[2]} END{print avg,loss}'\'')'
    instructions="${instructions//PING_COUNT/${wireguard_ping_sample_size}}"
    instructions="${instructions//PING_TARGET/${WIREGUARD_NETWORK_PREFIX}.1}"



    local ssh_result target proxypi_hostname upside_latency upside_loss downside_result downside_latency downside_loss entry
    for port in $(ssh::listen); do
        (
            ssh_result=$(ssh::execute_command "$port" "$instructions")
            read proxypi_hostname upside_latency upside_loss <<< "$ssh_result"
            local proxy_id=$((port - SSH_NETWORK_BASE + 2))
            target="${WIREGUARD_NETWORK_PREFIX}.${proxy_id}"


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
        \$(sudo wg show wg0 public-key)"

    local ssh_result proxypi_hostname proxypi_id proxypi_public_key

    # TODO (ahoone): No parallelization // RACE CONDITION ON WG SET WG0 PEER AND SAVE

    for port in $(ssh::listen); do
        ssh_result=$(ssh::execute_command "$port" "$instructions")
        read proxypi_hostname proxypi_public_key <<< "$ssh_result"
        local proxy_id=$((port - SSH_NETWORK_BASE + 2))

        if [ -z "$proxypi_public_key" ]; then
            echob "ProxyPi $proxypi_hostname have not been initialized (no public key)"
        else
            sudo wg set wg0 peer ${proxypi_public_key} allowed-ips ${WIREGUARD_NETWORK_PREFIX}.${proxy_id}/32 || return 1
            sudo wg-quick save wg0 2>/dev/null
        fi
    done

    sudo wg show | draw_box
}
