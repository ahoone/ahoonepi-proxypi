#!/bin/bash
source "../.env"

IP4=$(curl -s -4 ifconfig.me/ip)
IP6=$(curl -s -6 ifconfig.me/ip)
LAST_IP4_FILE="/home/admin/ddns/ip4_hist.txt"
LAST_IP6_FILE="/home/admin/ddns/ip6_hist.txt"

# IP4
if [ -f $LAST_IP4_FILE ]; then
    LAST_IP4=$(cat $LAST_IP4_FILE)
else
    LAST_IP4=""
fi

if [ "$IP4" != "$LAST_IP4" ]; then
    RESPONSE=$(curl -s -u "$OVH_USER:$OVH_PASS" "https://dns.eu.ovhapis.com/nic/update?system=dyndns&hostname=$OVH_HOST&myip=$IP4")
    echo "$(date): IPv4 - $RESPONSE" >> /home/admin/ddns/ovh_ddns.log
    echo $IP4 > $LAST_IP4_FILE
fi

# IP6
if [ -f $LAST_IP6_FILE ]; then
    LAST_IP6=$(cat $LAST_IP6_FILE)
else
    LAST_IP6=""
fi

if [ "$IP6" != "$LAST_IP6" ]; then
    RESPONSE=$(curl -s -u "$OVH_USER:$OVH_PASS" "https://dns.eu.ovhapis.com/nic/update?system=dyndns&hostname=$OVH_HOST&myip=$IP6")
    echo "$(date): IPv6 - $RESPONSE" >> /home/admin/ddns/ovh_ddns.log
    echo $IP6 > $LAST_IP6_FILE
fi
