#!/bin/bash

red="\033[91m"
endc="\033[0m"

time_warning_show() {
  echo "


      Installing additional software may take few minutes

"
}

sudo apt-get update && sudo apt-get --with-new-pkgs upgrade -y
sudo apt-get install libjpeg-dev libopenjp2-7-dev chrony htop iptables -y python*-venv
sudo apt autoremove -y
sudo chmod -R 777 "/home/${1}/RotorHazard" # to ensure smooth operation if files in RH directory were edited etc. and permissions changed
upgradeDate="$(date +%Y%m%d%H%M)"
cd /home/"${1}" || exit
if [ -d "/home/${1}/RotorHazard" ]; then
  # Control will enter here if $DIRECTORY exists.
  mv "/home/${1}/RotorHazard" "/home/${1}/RotorHazard_${upgradeDate}" || exit 1
fi
if [ -d "/home/${1}/RotorHazard-*" ]; then
  # Control will enter here if $DIRECTORY exists.
  mv "/home/${1}/RotorHazard-*" "/home/${1}/RotorHazard_${2}_${upgradeDate}" || exit 1
fi
sudo rm -r /home/"${1}"/temp.zip >/dev/null 2>&1 # in case of weird sys config or previous unsuccessful installations
cd /home/"${1}" || exit
if [ "$3" == "git" ]; then
  git clone -c advice.detachedHead=false -b "${2}" https://github.com/RotorHazard/RotorHazard.git
else
  wget https://codeload.github.com/RotorHazard/RotorHazard/zip/"${2}" -O temp.zip
  unzip temp.zip
  rm ~/wget* >/dev/null 2>&1
  mv /home/"${1}"/RotorHazard-* /home/"${1}"/RotorHazard
  sudo rm temp.zip
fi
sudo mkdir /home/"${1}"/backup_RH_data >/dev/null 2>&1
sudo chmod 777 -R /home/"${1}"/RotorHazard/src/server
sudo chmod 777 -R /home/"${1}"/RotorHazard_"${upgradeDate}"
sudo chmod 777 -R /home/"${1}"/backup_RH_data
sudo chmod 777 -R /home/"${1}"/.rhim_markers
sudo chmod 777 -R ~/RotorHazard
cp /home/"${1}"/RotorHazard_"${upgradeDate}"/src/server/config.json /home/"${1}"/RotorHazard/src/server/ >/dev/null 2>&1 &
cp -r /home/"${1}"/RotorHazard_"${upgradeDate}"/src/server/static /home/"${1}"/backup_RH_data
cp -r /home/"${1}"/RotorHazard_"${upgradeDate}"/src/server/static/user/* /home/"${1}"/RotorHazard/src/server/static/user/ || printf "\n no user folder found in this RotorHazard version - skipping \n" #rh_pr
mkdir /home/"${1}"/RotorHazard/src/server/db_bkp
cp -r /home/"${1}"/RotorHazard_"${upgradeDate}"/src/server/db_bkp/* /home/"${1}"/RotorHazard/src/server/db_bkp/ || printf "\n no backup folder found in this RotorHazard version - skipping \n" #rh_pr
cp -r /home/"${1}"/RotorHazard_"${upgradeDate}"/src/server/static/image /home/"${1}"/RotorHazard/src/server/static/image
cp /home/"${1}"/RotorHazard_"${upgradeDate}"/src/server/config.json /home/"${1}"/backup_RH_data >/dev/null 2>&1 &
cp /home/"${1}"/RotorHazard_"${upgradeDate}"/src/server/database.db /home/"${1}"/RotorHazard/src/server/ >/dev/null 2>&1 &
cp /home/"${1}"/RotorHazard_"${upgradeDate}"/src/server/database.db /home/"${1}"/backup_RH_data >/dev/null 2>&1 &
time_warning_show
cd /home/"${1}"/RotorHazard/src/server || echo "$red missing RotorHazard directory $endc"
pip3 install --upgrade pip
pip3 install --upgrade --no-cache-dir -r requirements.txt
pip3 install cffi pillow

cd /home/"${1}"/RH_Install-Manager/scripts/ || exit
sudo ./python3_transition.sh "${1}"

# port forwarding
if ! grep -q "sudo iptables -A PREROUTING -t nat -p tcp --dport 8080 -j REDIRECT --to-ports 80" /etc/rc.local; then
  cd /home/"${1}"/RH_Install-Manager/scripts/ || exit
  sudo ./iptables_conf.sh
fi

cd /home/"${1}" || exit
