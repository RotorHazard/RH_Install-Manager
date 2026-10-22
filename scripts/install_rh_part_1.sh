#!/bin/bash

# Recheck the effective runtime even when invoked directly. No ambient interpreter fallback.
python3 -I -B "$(dirname "$0")/../runtime_preflight.py" part1 "$1" "$2" "$4" ${5:+"$5"} || exit 1
# $1 is linux user name
# $2 is actual version of RotorHazard to get.

sudo dpkg --configure -a
sudo apt --fix-broken install
sudo apt-get update && sudo apt-get --with-new-pkgs upgrade -y
sudo apt autoremove -y
sudo apt install wget python3 python*-venv chrony htop libjpeg-dev libffi-dev build-essential git scons swig zip i2c-tools libopenjp2-7-dev python3-smbus python3-smbus2 python3-pip python3-dev iptables -y
sudo apt install python3-rpi.gpio -y || echo "-- no python-rpi.gpio module found - available only on Pi --" #is this redundant?
sudo rm -r /home/"${1}"/temp.zip >/dev/null 2>&1 # in case of weird sys config or previous unsuccessful installations
cd /home/"${1}" || exit
sudo /home/"${1}"/RH_Install-Manager/scripts/move_old_rh_dirs.sh "${1}" "${2}"
if [ ! -e "/home/${1}/.venv" ] && [ ! -L "/home/${1}/.venv" ]; then
  "$4" -I -B -m venv --system-site-packages "/home/${1}/.venv" || exit 1
fi
