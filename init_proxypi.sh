pipx install --editable cli/. --force
# we keep the editable to avoid having to recompile the library
# if we update the general config (SSH_NETWORK_BASE)
pipx ensurepath
proxypi --install-completion

exit
