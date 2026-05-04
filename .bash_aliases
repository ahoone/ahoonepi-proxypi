source proxypi.sh

proxypi() {
    /home/admin/proxypi.sh "$@"
}

_proxypi_completion() {
    local cur="${COMP_WORDS[COMP_CWORD]}"
    local opts="${!FCT_MAP[@]}"
    COMPREPLY=( $(compgen -W "$opts"  "$cur") )
}

complete -F _proxypi_completion proxypi
