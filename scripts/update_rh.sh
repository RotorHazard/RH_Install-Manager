#!/bin/bash

# Direct entries and coordinator children share the same validated descriptor lock.
if [ -z "${RHIM_SOURCE_PAYLOAD:-}" ]; then
  exec python3 -I -B "$(dirname "$0")/../source_safety.py" update "$@"
fi
python3 -I -B "$(dirname "$0")/../source_safety.py" verify-lock "$1" || exit 1

if [ "$RHIM_SOURCE_PAYLOAD" = host ]; then
  sudo apt-get update || { echo "Package index update failed" >&2; exit 1; }
  sudo apt-get --with-new-pkgs upgrade -y || { echo "Host package upgrade failed" >&2; exit 1; }
  sudo apt-get install libjpeg-dev libopenjp2-7-dev chrony htop iptables unzip wget git -y python*-venv || { echo "Required dependency installation failed" >&2; exit 1; }
  sudo apt autoremove -y || { echo "Package cleanup failed" >&2; exit 1; }
  python3 -I -B "$(dirname "$0")/../runtime_preflight.py" update "$1" "$2" "$4" ${5:+"$5"} || exit 1
  cd "$RHIM_PREPARED_SOURCE/src/server" || { echo "$red missing RotorHazard directory $endc"; exit 1; }
  "$4" -I -B -m pip install --upgrade pip || { echo "Pip upgrade failed" >&2; exit 1; }
  "$4" -I -B -m pip install --upgrade --no-cache-dir -r requirements.txt || { echo "RotorHazard dependency installation failed" >&2; exit 1; }
  "$4" -I -B -m pip install cffi pillow || { echo "Additional Python dependency installation failed" >&2; exit 1; }
  exit 0
fi
[ "$RHIM_SOURCE_PAYLOAD" = activate ] || exit 1
cd /home/"${1}" || exit 1
cd /home/"${1}"/RH_Install-Manager/scripts/ || exit
# Preflight accepts only an existing Python 3 venv service; legacy migration would invalidate that check.

# port forwarding
sudo ./iptables_conf.sh || exit 1

cd /home/"${1}" || exit
