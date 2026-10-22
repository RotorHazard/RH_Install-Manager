#!/bin/bash

# Recheck the effective runtime even when invoked directly. No ambient interpreter fallback.
python3 -I -B "$(dirname "$0")/../runtime_preflight.py" part2 "$1" "$2" "$4" ${5:+"$5"} || exit 1
# $1 is linux user name
# $2 is actual version of RotorHazard to get.

red="\033[91m"
green="\033[92m"
endc="\033[0m"

sudo /home/"${1}"/RH_Install-Manager/scripts/move_old_rh_dirs.sh "${1}" "${2}" || exit 1

sudo dpkg --configure -a || { echo "Package configuration failed" >&2; exit 1; }
sudo apt --fix-broken install || { echo "Package repair failed" >&2; exit 1; }
cd /home/"${1}" || exit
if [ "$3" == "git" ]; then
  git clone -c advice.detachedHead=false -b "${2}" https://github.com/RotorHazard/RotorHazard.git || { echo "RotorHazard clone failed" >&2; exit 1; }
else
  wget https://codeload.github.com/RotorHazard/RotorHazard/zip/"${2}" -O temp.zip || { echo "RotorHazard download failed" >&2; exit 1; }
  unzip temp.zip || { echo "RotorHazard archive extraction failed" >&2; exit 1; }
  rm ~/wget* >/dev/null 2>&1
  mv /home/"${1}"/RotorHazard-* /home/"${1}"/RotorHazard || exit 1
fi
printf "\n\n   Installing additional software - may take few minutes \n\n\n"
cd /home/"${1}"/RotorHazard/src/server || { echo "$red missing RotorHazard directory"; exit 1; }
"$4" -I -B -m pip install --upgrade pip || { echo "Pip upgrade failed" >&2; exit 1; }
"$4" -I -B -m pip install --upgrade --no-cache-dir -r requirements.txt || { echo "RotorHazard dependency installation failed" >&2; exit 1; }
"$4" -I -B -m pip install cffi pillow || { echo "Additional Python dependency installation failed" >&2; exit 1; }
sudo chmod 777 -R /home/"${1}"/RotorHazard/src/server || { echo "RotorHazard permissions update failed" >&2; exit 1; }
cd /home/"${1}" || exit

# added because of the broken Adafruit_GPIO compatibility on Raspbian 11 Bullseye
for platform_file in /usr/local/lib/python3*/dist-packages/Adafruit_GPIO/Platform.py; do
  if [ -e "$platform_file" ]; then
    sudo sed -i 's/UNKNOWN          = 0/UNKNOWN          = 1/' "$platform_file" || { echo "Adafruit_GPIO compatibility update failed" >&2; exit 1; }
  fi
done

java_installation() {
  if [[ $(~/RH_Install-Manager/scripts/pi_model_check.sh) == "pi_zero" ]]; then
    sudo apt-get install openjdk-8-jdk-headless -y
  else
    sudo apt-get install default-jdk-headless -y
  fi
}

java_installation || echo "Optional Java installation failed. RotorHazard setup will continue." >&2

# run as a service
cd /home/"${1}"/RH_Install-Manager/scripts/ || exit
sudo /home/"${1}"/RH_Install-Manager/scripts/system_service_add.sh "${1}" || { echo "RotorHazard service creation failed" >&2; exit 1; }
echo

sudo chmod 644 /lib/systemd/system/rotorhazard.service || { echo "Service permissions update failed" >&2; exit 1; }
sudo systemctl daemon-reload || { echo "Service daemon reload failed" >&2; exit 1; }
sudo systemctl enable rotorhazard.service || { echo "RotorHazard service enabling failed" >&2; exit 1; }
echo

# port forwarding
cd /home/"${1}"/RH_Install-Manager/scripts/ || exit
sudo /home/"${1}"/RH_Install-Manager/scripts/iptables_conf.sh || exit 1

sed -i '/shell_hello_1.txt/d' ~/.bashrc || { echo "Shell greeting cleanup failed" >&2; exit 1; }
sed -i '/shell_hello_2.txt/d' ~/.bashrc || { echo "Shell greeting cleanup failed" >&2; exit 1; }
echo "cat ~/RH_Install-Manager/resources/shell_hello_2.txt" >> ~/.bashrc || { echo "Shell greeting update failed" >&2; exit 1; }
