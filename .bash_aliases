proxypi() {
    /home/admin/proxypi.sh "$@"
}
_proxypi_completion() {
    local cur="${COMP_WORDS[COMP_CWORD]}"
    local opts="swarm-execute ping apt-update apt-upgrade git-pull ping-wireguard load-wireguard load-ssh connect"
    COMPREPLY=( $(compgen -W "$opts"  "$cur") )
}
complete -F _proxypi_completion proxypi
