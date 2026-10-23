#!/bin/bash

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
sudo iptables-save || { echo "Reading firewall rules failed" >&2; exit 1; }

if { [ -e /etc/rc.local ] || [ -L /etc/rc.local ]; } &&
   [ ! -e /etc/rc.local.iptables1_saved ] && [ ! -L /etc/rc.local.iptables1_saved ]; then
  sudo cp /etc/rc.local /etc/rc.local.iptables1_saved || { echo "rc.local backup failed" >&2; exit 1; }
fi

sudo tee /etc/rc.local > /dev/null << 'EOF' || { echo "Port forwarding configuration write failed" >&2; exit 1; }
#!/bin/bash

# [Port Forwarding – RH_Install-Manager]
iptables -A PREROUTING -t nat -p tcp --dport 80 -j REDIRECT --to-ports 5000
iptables -A PREROUTING -t nat -p tcp --dport 8080 -j REDIRECT --to-ports 80
iptables-save

exit 0
EOF

sudo chmod +x /etc/rc.local || { echo "rc.local permissions update failed" >&2; exit 1; }

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
