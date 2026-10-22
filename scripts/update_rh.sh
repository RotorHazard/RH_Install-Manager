#!/bin/bash

# Recheck the effective runtime even when invoked directly. No ambient interpreter fallback.
python3 -I -B "$(dirname "$0")/../runtime_preflight.py" update "$1" "$2" "$4" ${5:+"$5"} || exit 1

red="\033[91m"
endc="\033[0m"

time_warning_show() {
  echo "


      Installing additional software may take few minutes

"
}

sudo apt-get update || { echo "Package index update failed" >&2; exit 1; }
sudo apt-get --with-new-pkgs upgrade -y || { echo "Host package upgrade failed" >&2; exit 1; }
sudo apt-get install libjpeg-dev libopenjp2-7-dev chrony htop iptables -y python*-venv || { echo "Required dependency installation failed" >&2; exit 1; }
sudo apt autoremove -y || { echo "Package cleanup failed" >&2; exit 1; }
sudo chmod -R 777 "/home/${1}/RotorHazard" || { echo "RotorHazard permissions update failed" >&2; exit 1; }
upgradeDate="$(date +%Y%m%d%H%M)"
cd /home/"${1}" || exit
if [ -d "/home/${1}/RotorHazard" ]; then
  # Control will enter here if $DIRECTORY exists.
  if [ -e "/home/${1}/RotorHazard_${upgradeDate}" ] || [ -L "/home/${1}/RotorHazard_${upgradeDate}" ]; then
    echo "RotorHazard backup already exists. Move it to a safe location before retrying." >&2
    exit 1
  fi
  mv -T "/home/${1}/RotorHazard" "/home/${1}/RotorHazard_${upgradeDate}" || { echo "RotorHazard backup move failed" >&2; exit 1; }
fi
sudo rm -f /home/"${1}"/temp.zip || { echo "Temporary archive cleanup failed" >&2; exit 1; }
cd /home/"${1}" || exit
if [ "$3" == "git" ]; then
  git clone -c advice.detachedHead=false -b "${2}" https://github.com/RotorHazard/RotorHazard.git || { echo "RotorHazard clone failed" >&2; exit 1; }
else
  wget https://codeload.github.com/RotorHazard/RotorHazard/zip/"${2}" -O temp.zip || { echo "RotorHazard download failed" >&2; exit 1; }
  unzip -o temp.zip || { echo "RotorHazard archive extraction failed" >&2; exit 1; }
  rm ~/wget* >/dev/null 2>&1
  mv /home/"${1}"/RotorHazard-* /home/"${1}"/RotorHazard || { echo "RotorHazard source move failed" >&2; exit 1; }
  sudo rm temp.zip || { echo "Temporary archive cleanup failed" >&2; exit 1; }
fi
sudo mkdir -p /home/"${1}"/backup_RH_data || { echo "Data backup directory creation failed" >&2; exit 1; }
sudo chmod 777 -R /home/"${1}"/RotorHazard/src/server /home/"${1}"/RotorHazard_"${upgradeDate}" /home/"${1}"/backup_RH_data || { echo "Data directory permissions update failed" >&2; exit 1; }
old_server="/home/${1}/RotorHazard_${upgradeDate}/src/server"
new_server="/home/${1}/RotorHazard/src/server"
for file in config.json database.db; do
  if [ -e "$old_server/$file" ] || [ -L "$old_server/$file" ]; then
    cp "$old_server/$file" "$new_server/" || { echo "Could not restore $file" >&2; exit 1; }
    cp "$old_server/$file" "/home/${1}/backup_RH_data/" || { echo "Could not back up $file" >&2; exit 1; }
  fi
done
if [ -e "$old_server/static" ] || [ -L "$old_server/static" ]; then
  cp -r "$old_server/static" "/home/${1}/backup_RH_data/" || { echo "Static data backup failed" >&2; exit 1; }
fi
for directory in static/user db_bkp static/image; do
  if [ -e "$old_server/$directory" ] || [ -L "$old_server/$directory" ]; then
    mkdir -p "$new_server/$directory" || { echo "Could not create $directory" >&2; exit 1; }
    cp -r "$old_server/$directory/." "$new_server/$directory/" || { echo "Could not restore $directory" >&2; exit 1; }
  fi
done
time_warning_show
cd /home/"${1}"/RotorHazard/src/server || { echo "$red missing RotorHazard directory $endc"; exit 1; }
"$4" -I -B -m pip install --upgrade pip || { echo "Pip upgrade failed" >&2; exit 1; }
"$4" -I -B -m pip install --upgrade --no-cache-dir -r requirements.txt || { echo "RotorHazard dependency installation failed" >&2; exit 1; }
"$4" -I -B -m pip install cffi pillow || { echo "Additional Python dependency installation failed" >&2; exit 1; }

cd /home/"${1}"/RH_Install-Manager/scripts/ || exit
# Preflight accepts only an existing Python 3 venv service; legacy migration would invalidate that check.

# port forwarding
if ! grep -q "sudo iptables -A PREROUTING -t nat -p tcp --dport 8080 -j REDIRECT --to-ports 80" /etc/rc.local; then
  cd /home/"${1}"/RH_Install-Manager/scripts/ || exit
  sudo ./iptables_conf.sh || exit 1
fi

cd /home/"${1}" || exit
