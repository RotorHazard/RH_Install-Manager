#!/bin/bash

# Validate and persist before changing the running firewall.
forwarding_mode=$(sudo python3 -I -B "$(dirname "$0")/../rc_local.py") || exit 1
case "$forwarding_mode" in
  external)
    echo "RHIM: port forwarding is externally managed; configuration and reachability are the operator's responsibility."
    exit 0
    ;;
  managed) ;;
  *) echo "Invalid forwarding mode from rc.local helper" >&2; exit 1 ;;
esac

ensure_forwarding_rule() {
  local status
  sudo iptables -C PREROUTING -t nat -p tcp --dport "$1" -j REDIRECT --to-ports "$2"
  status=$?
  if [ "$status" -eq 1 ]; then
    sudo iptables -A PREROUTING -t nat -p tcp --dport "$1" -j REDIRECT --to-ports "$2" || return 1
  elif [ "$status" -ne 0 ]; then
    echo "Checking port $1 forwarding failed (status $status)" >&2
    return 1
  fi
}

ensure_forwarding_rule 80 5000 || { echo "Port 80 forwarding failed" >&2; exit 1; }
ensure_forwarding_rule 8080 80 || { echo "Port 8080 forwarding failed" >&2; exit 1; }

green="\033[92m"
red="\033[91m"
endc="\033[0m"
under="\033[4m"
orange="\033[33m"
blue="\033[94m"

printf "

$blue
port forwarding added - server available on default port 80
no need to type server port number in a browser address bar
just type RotorHazard server IP address:
$endc
$under$(hostname -I | awk '{ print $1 }')$endc
$under$(hostname -I | awk '{ print $2 }')$endc
$under$(hostname -I | awk '{ print $3 }')$endc
$endc

$orange(services that run on port 80 are available on port 8080 now)$endc"
