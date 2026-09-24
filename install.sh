#!/usr/bin/env bash

set -euo pipefail

# Check out the pi-hole installer from
# which I reused much of the code snippets
# https://github.com/pi-hole/pi-hole

####################################################################################################
####################################################################################################


REPO_URL="https://github.com/ahoone/ahoonepi-proxypi.git"
BRANCH="${PROXYPI_BRANCH:-main}"
INSTALLER_URL="https://raw.githubusercontent.com/ahoone/ahoonepi-proxypi/$BRANCH/install.sh"
INSTALL_DIR="/opt/ahoonepi-proxypi"
LIGHTHOUSE_DUMMY_USER="proxypi-dummy"
LIGHTHOUSE_SERVICE_USER="proxypi-service"
LIGHTHOUSE_OPERATORS_GROUP="proxypi-operators"


####################################################################################################
####################################################################################################

preflight() {
    local os_ids pretty
    os_ids=$(. /etc/os-release && echo " $ID ${ID_LIKE:-} ")
    pretty=$(. /etc/os-release && echo "${PRETTY_NAME:-unknown}")
    if [[ $os_ids != *" debian "* ]]; then
        echo "Unsupported OS: $pretty. A Debian-based system is required (Debian, Raspberry Pi OS, Ubuntu)." >&2
        exit 1
    fi

    if [[ ! -d /run/systemd/system ]]; then
        echo "systemd is not the init system here; the services cannot be installed." >&2
        exit 1
    fi
}

preflight

####################################################################################################
####################################################################################################


CLEAR='\e[0m'
COL_YELLOW='\e[0;33m'
COL_BOLD_RED='\e[1;31m'
COL_BOLD_GREEN='\e[1;32m'
TICK="[${COL_BOLD_GREEN}✓${CLEAR}]"
CROSS="[${COL_BOLD_RED}✗${CLEAR}]"
INFO="[i]"


####################################################################################################
####################################################################################################

SCRIPT_PATH="${BASH_SOURCE[0]:-}"  # empty when piped, real path when run from a file

takeoff() {
    if [[ "${EUID}" -eq 0 ]]; then
        printf "  %b Starting the installation...\n" "${INFO}"
        return
    elif ! command -v sudo >/dev/null 2>&1; then
        printf "  %b %bCommand sudo does not exist%b\n" "${INFO}" "${COL_BOLD_RED}" "${CLEAR}"
        printf "      The installer can not elevate its privileges\n"
    elif sudo -v; then
        printf "  %b Restarting the installer as root...\n" "${INFO}"
        if [[ -f "$SCRIPT_PATH" ]]; then
            exec sudo env PROXYPI_BRANCH="$BRANCH" bash "$SCRIPT_PATH"
        else
            curl -fsSL "$INSTALLER_URL" | sudo env PROXYPI_BRANCH="$BRANCH" bash
            exit $?
        fi
    else
        printf "  %b %bScript called with non-root privileges%b\n" "${INFO}" "${COL_BOLD_RED}" "${CLEAR}"
        printf "      %bahoonepi-proxypi%b requires elevated privileges to be installed\n" "${COL_BOLD_RED}" "${CLEAR}"
        printf "      Please check the installer for any concerns regarding this requirement\n"
        printf "      Make sure to download this script from a trusted source\n"
        printf "      Please re-run the installer as root: %bcurl -fsSL %s | sudo bash%b\n" "${COL_YELLOW}" "${INSTALLER_URL}" "${CLEAR}"
        exit 1
    fi
}

takeoff

####################################################################################################
####################################################################################################



# THIS SCRIPTS SHOULD BE RUN AS ROOT
# THEN THE POST-INSTALL SCRIPT WILL RUN AS NON-ROOT


check_group_exists() {
    getent group "$1"
}

check_user_exists() {
    id -u "$1" >/dev/null 2>&1
}


check_user_is_root() {
    local uid
    uid=$(id -u "$1") || exit 1
    (( uid == 0 ))
}



create_dummy_user() {
    if ! check_user_exists "$LIGHTHOUSE_DUMMY_USER"; then
        useradd \
            --system \
            --user-group \
            --home-dir "/nonexistent" \
            --shell "/usr/sbin/nologin" \
            --comment "ahoonepi-proxypi tunnel endpoint" \
            "$LIGHTHOUSE_DUMMY_USER"

        return 0
    fi


}



check_uv_is_installed() {
    local is_installed="$(command -v uv > /dev/null && echo "true" || echo "false")"
    printf "$is_installed\n"
}


main() {


    printf "  %b Sudo utility check\n" "${INFO}"

    apt-get update
    apt-get install openssh-server
    systemctl enable --now ssh

    check_uv_is_installed

    create_dummy_user

}

main

# if [ "$(id -u)" -eq 0 ]; then
#     echo "Run this as your normal sudo-capable user, not as root." >&2
#     exit 1
# fi

# if [ -d "$INSTALL_DIR/.git" ]; then
#     echo "Already installed at $INSTALL_DIR — updating instead of cloning."
#     sudo git -C "$INSTALL_DIR" fetch origin "$BRANCH"
#     sudo git -C "$INSTALL_DIR" checkout "$BRANCH"
#     sudo git -C "$INSTALL_DIR" reset --hard "origin/$BRANCH"
# else
#     sudo git clone --branch "$BRANCH" "$REPO_URL" "$INSTALL_DIR"
# fi

# sudo chown -R root:root "$INSTALL_DIR"
# sudo chmod -R go-w "$INSTALL_DIR"

# echo "✓ $INSTALL_DIR ready at branch $BRANCH"

# command -v uv > /dev/null ||echo "`uv` is not installed" && exit 1

# proxypi --install-completion


# install via uv the cli
#
# install the repository
