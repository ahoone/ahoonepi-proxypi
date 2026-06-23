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
