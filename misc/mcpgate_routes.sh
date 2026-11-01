#!/bin/bash
###########################################################
# mcp-gate01 return-route setup
# Run ON mcp-gate01 (console or via a k8s-node jump host).
#
# mcp-gate01 is dual-homed:
#   eth0  TELUS Fibe LAN (192.168.1.0/24), DHCP default, metric 100
#   eth1  home lab       (192.168.30.0/24), static default, metric 101
# Replies to clients on other home networks match only the lowest-metric
# default, so they leave via eth0 and the Fibe router drops them (they look
# like unsolicited packets on its WAN side). Clients on 192.168.30.0/24 work
# because that route is directly connected on eth1.
# Fix: pin each home network to the lab router (192.168.30.1) on eth1.
# The central router can then log all traffic to this host.
#
# Not an Ansible playbook on purpose: Ansible reaches this host over these
# routes, so they must exist before it can run.
##########################################################

# --- Configuration ---------------------------------------
DEVICE="eth1"
GATEWAY="192.168.30.1"
NETWORKS=(192.168.10.0/24 192.168.20.0/24 192.168.40.0/24)
# ---------------------------------------------------------

set -euo pipefail

# Connection names ("Wired connection 2") are auto-generated and can shuffle,
# so look the profile up by device.
CON="$(nmcli -g GENERAL.CONNECTION device show "$DEVICE")"
if [ -z "$CON" ]; then
  echo "No active NetworkManager connection on $DEVICE" >&2
  exit 1
fi
echo "Using connection '$CON' on $DEVICE"

for net in "${NETWORKS[@]}"; do
  if nmcli -g ipv4.routes con show "$CON" | grep -qF "$net $GATEWAY"; then
    echo "$net already present, skipping"
  else
    echo "Adding $net via $GATEWAY"
    sudo nmcli con mod "$CON" +ipv4.routes "$net $GATEWAY"
  fi
done

sudo nmcli device reapply "$DEVICE"

echo
echo "Routes now stored on '$CON':"
nmcli -g ipv4.routes con show "$CON"
echo
echo "Live table:"
ip route | grep "via $GATEWAY"
