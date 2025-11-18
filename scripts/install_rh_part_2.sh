#!/bin/bash
# $1 is linux user name
# $2 is actual version of RotorHazard to get.

red="\033[91m"
green="\033[92m"
endc="\033[0m"

sudo /home/"${1}"/RH_Install-Manager/scripts/move_old_rh_dirs.sh "${1}" "${2}"

sudo dpkg --configure -a
sudo apt --fix-broken install
cd /home/"${1}" || exit
if [ "$3" == "git" ]; then
  git clone -c advice.detachedHead=false -b "${2}" https://github.com/RotorHazard/RotorHazard.git
else
  wget https://codeload.github.com/RotorHazard/RotorHazard/zip/"${2}" -O temp.zip
  unzip temp.zip
  rm ~/wget* >/dev/null 2>&1
  mv /home/"${1}"/RotorHazard-* /home/"${1}"/RotorHazard || exit 1
fi
printf "\n\n   Installing additional software - may take few minutes \n\n\n"
cd /home/"${1}"/RotorHazard/src/server || echo "$red missing RotorHazard directory"
pip3 install --upgrade pip
pip3 install --upgrade --no-cache-dir -r requirements.txt
pip3 install cffi pillow
sudo chmod 777 -R /home/"${1}"/RotorHazard/src/server
cd /home/"${1}" || exit

# added because of the broken Adafruit_GPIO compatibility on Raspbian 11 Bullseye
(sudo sed -i 's/UNKNOWN          = 0/UNKNOWN          = 1/' /usr/local/lib/python3*/dist-packages/Adafruit_GPIO/Platform.py &&
  printf "\n $green Adafruit_GPIO compatibility is now OK $endc \n\n\n" && sleep 1) ||
  (printf "$endc \nAdafruit_GPIO compatibility file probably missing - skipping\n\n $endc" && sleep 2)

java_installation() {
  if [[ $(~/RH_Install-Manager/scripts/pi_model_check.sh) == "pi_zero" ]]; then
    sudo apt-get install openjdk-8-jdk-headless -y
  else
    sudo apt-get install default-jdk-headless -y
  fi
}

java_installation

# run as a service
sudo rm /lib/systemd/system/rotorhazard.service >/dev/null 2>&1
cd /home/"${1}"/RH_Install-Manager/scripts/ || exit
sudo /home/"${1}"/RH_Install-Manager/scripts/system_service_add.sh "${1}"
echo

sudo chmod 644 /lib/systemd/system/rotorhazard.service
sudo systemctl daemon-reload
sudo systemctl enable rotorhazard.service
echo

# port forwarding
cd /home/"${1}"/RH_Install-Manager/scripts/ || exit
sudo /home/"${1}"/RH_Install-Manager/scripts/iptables_conf.sh

sed -i '/shell_hello_1.txt/d' ~/.bashrc
sed -i '/shell_hello_2.txt/d' ~/.bashrc  # in case of previous installations
echo "cat ~/RH_Install-Manager/resources/shell_hello_2.txt" >> ~/.bashrc 2>/dev/null