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
