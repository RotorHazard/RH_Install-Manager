#!/bin/bash

##################
### fun stuff
dots7() { # done that way so it work on every terminal
  for _ in {1..7}; do
    printf "."
    sleep 0.2
  done
  printf "\n"
}

##################

print_info_message() {
  printf "\n"
  printf "dependencies will be auto-detected and installed \n"
  printf "installing dependencies may need 'sudo' password\n"
}

check_for_new_rhim() {

  if ! test -f .first_time_here; then
    wget https://raw.githubusercontent.com/RotorHazard/Install-Manager/stable/version.txt -q -O ~/RH_Install-Manager/.new_rhim_version_check_file.txt
    diff ~/RH_Install-Manager/version.txt ~/RH_Install-Manager/.new_rhim_version_check_file.txt >~/RH_Install-Manager/.new_rhim_version_diff_file
  else
    sudo apt update || printf "repositories have not been updated \n"
  fi
}

open_software_alias_check() {

  if ! grep -q "alias rhim=" ~/.bashrc; then
    echo '
#[added during RH_Install-Manager setup]
alias rhim="cd ~/RH_Install-Manager && sh ./rhim.sh"                        # opens RH_Install-Manager software' >> ~/.bashrc
  fi

  if ! grep -q "~/.venv/bin/activate" ~/.bashrc; then
    echo '
#[added during RH_Install-Manager setup]
alias rh="cd ~/RotorHazard/src/server && source ~/.venv/bin/activate && python3 server.py"   # starts RH-server' >> ~/.bashrc
  fi
}

dependencies_check() {

  check_package() {
    if dpkg-query -l "$1" >/dev/null 2>&1; then
      return 0
    else
      return 1
    fi

  }

  # done this way due to the bug when checking some packages
  check_package_when_errors() {
    if dpkg-query -l "$1" | grep ii >/dev/null 2>&1; then
      return 0
    else
      return 1
    fi

  }

  check_python_package() {
    if python3 -c "import $1" >/dev/null 2>&1; then
      return 0
    else
      return 1
    fi
  }

  which git >/dev/null
  if [ $? -gt 0 ]; then
    echo git has to be installed && sudo apt install git -y || return 1
  else
    echo git"               "found # those  cure my ocd
  fi

  which python3 >/dev/null
  if [ $? -gt 0 ]; then
    echo python3 has to be installed && sudo apt install python3 -y || return 1
  else
    echo python3"           "found # those  cure my ocd
  fi

  which avrdude >/dev/null
  if [ $? -gt 0 ]; then
    echo avrdude has to be installed && sudo apt install avrdude -y
  else
    echo avrdude"           "found
  fi

  which curl >/dev/null
  if [ $? -gt 0 ]; then
    echo curl has to be installed && sudo apt install curl -y
  else
    echo curl"              "found
  fi

  which cowsay >/dev/null
  if [ $? -gt 0 ]; then
    echo cowsay has to be installed && sudo apt install cowsay -y
  else
    echo cowsay"            "found
  fi

  which jq >/dev/null
  if [ $? -gt 0 ]; then
    echo jq has to be installed && sudo apt install jq -y
  else
    echo jq"                "found
  fi

  which pip3 >/dev/null
  if [ $? -gt 0 ]; then
    echo pip3 package has to be installed && sudo apt install python3-pip -y || return 1
  else
    echo pip3"              "found
  fi

  if check_package 'procps'; then
    echo procps"            "found
  else
    echo procps has to be installed && sudo apt install procps -y
  fi

  if check_package 'fonts-symbola'; then
    echo fonts-symbola"     "found
  else
    echo fonts-symbola has to be installed && sudo apt install fonts-symbola -y
  fi

  if check_package 'i2c-tools'; then
    echo i2c-tools"         "found
  else
    echo i2c-tools has to be installed && sudo apt install i2c-tools -y
  fi

  if check_python_package 'wheel'; then
    echo wheel"             "found
  else
    echo wheel has to be installed && sudo apt install python3-wheel -y
  fi

  if check_python_package 'requests'; then
    echo requests"          "found
  else
    echo requests has to be installed && sudo apt install python3-requests -y || return 1
  fi

  if check_package 'python3-gpiozero'; then
    echo python3-gpiozero"  "found
  else
    echo python3-gpiozero has to be installed && sudo apt install python3-gpiozero -y
  fi

  if check_package_when_errors 'python3-requests'; then
    echo python3-requests"  "found
  else
    echo python3-requests has to be installed && sudo apt install python3-requests -y || return 1
  fi

  if check_package 'python3-dev'; then
    echo python3-dev"       "found
  else
    echo python3-dev has to be installed && sudo apt install python3-dev -y
  fi

  if check_package_when_errors 'python3-venv'; then
    echo python3-venv"      "found
  else
    echo python3-venv has to be installed && sudo apt install python3-venv -y || return 1
  fi

  if check_package 'python3-smbus2'; then
    echo python3-smbus2"    "found
  else
    echo python3-smbus2 has to be installed && sudo apt install python3-smbus2 -y
  fi

  if check_package 'python3-smbus'; then
    echo python3-smbus"     "found
  else
    echo python3-smbus has to be installed && sudo apt install python3-smbus -y
  fi

  if check_python_package 'RPi.GPIO'; then
    echo RPi.GPIO"          "found
  else
    echo RPi.GPIO has to be installed && sudo apt install python3-rpi.gpio -y || echo - only on Pi -
  fi

}

print_info_message
check_for_new_rhim
open_software_alias_check &
dependencies_check || exit $?
wait
# RH venv creation belongs to validated installation part 1; legacy flags do not trigger migration.
if [ "$1" != "no_start" ]; then
  python3 start_rhim.py
  exit $?
fi
