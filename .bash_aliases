PROXYPI_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

source "$PROXYPI_DIR/proxypi.sh"

proxypi() {
    "$PROXYPI_DIR/proxypi.sh" "$@"
}

_proxypi_completion() {
    local cur="${COMP_WORDS[COMP_CWORD]}"
    local opts="${!FCT_MAP[@]}"
    COMPREPLY=( $(compgen -W "$opts" "$cur") )
}

complete -F _proxypi_completion proxypi
