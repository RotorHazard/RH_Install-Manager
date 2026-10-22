#!/bin/bash

export PYTHONPATH=/home/"$USER"/RH_Install-Manager:$PYTHONPATH

sh ~/RH_Install-Manager/rhim.sh no_start || exit $?
if [ "$1" == "wifi" ]; then
  sh ~/RH_Install-Manager/NuclearHazard/nh-wifi.sh
else
  export INSTALL_STEP="$1"
  python3 ~/RH_Install-Manager/NuclearHazard/nh-quick-install.py
fi
