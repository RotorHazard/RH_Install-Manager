#!/bin/bash

set -o pipefail

hotspot_error() {
    echo "Hotspot configuration failed: $1" >&2
    exit 1
}

[ "$#" -eq 2 ] || hotspot_error "Expected SSID and password arguments."

hotspot_script="/home/$USER/hotspot.sh"
sudo install -m 700 /dev/null "$hotspot_script" || hotspot_error "Cannot prepare hotspot script."
{
    printf '#!/bin/bash\n'
    printf 'ssid=%q\npassword=%q\n' "$1" "$2"
    cat <<'HOTSPOT'
if iwgetid -r | grep -q .; then
    echo "Wi-Fi network found. Not creating a hotspot."
else
    nmcli dev wifi hotspot ifname wlan0 ssid "$ssid" password "$password"
fi
HOTSPOT
} | sudo tee "$hotspot_script" >/dev/null || hotspot_error "Cannot write hotspot script."

sudo tee /etc/systemd/system/hotspot.service >/dev/null <<SERVICE || hotspot_error "Cannot write hotspot service."
[Unit]
Description=Hotspot Service
After=NetworkManager.service
Wants=NetworkManager.service

[Service]
Type=simple
ExecStartPre=/bin/sleep 10
ExecStart=sudo /home/$USER/hotspot.sh
WorkingDirectory=/home/$USER/

[Install]
WantedBy=multi-user.target
SERVICE
sudo systemctl daemon-reload || hotspot_error "Cannot reload systemd services."
sudo systemctl enable hotspot.service || hotspot_error "Cannot enable hotspot service."

echo "


--- Automatic NuclearHazard AccessPoint enabled ---

"
