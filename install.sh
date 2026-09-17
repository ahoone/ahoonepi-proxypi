#!/bin/bash


git clone https://github.com/ahoone/ahoonepi-proxypi /opt/ahoonepi-proxypi


command -v uv > /dev/null ||echo "`uv` is not installed" && exit 1

proxypi --install-completion


# install via uv the cli
#
# install the repository
