echo "

[Unit]
Description=RotorHazard Server
After=multi-user.target

[Service]
User=${1}
WorkingDirectory=/home/${1}/RotorHazard/src/server
ExecStart=/home/${1}/.venv/bin/python3 server.py

[Install]
WantedBy=multi-user.target

" | sudo tee /lib/systemd/system/rotorhazard.service
