#!/bin/bash
read -r command
output=$(/home/admin/proxypi.sh $command)
echo "$output"
