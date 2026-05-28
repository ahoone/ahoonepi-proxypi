#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

read -r command

output=$("$SCRIPT_DIR/proxypi.sh" $command)

echo "$output"
