#!/bin/bash

green="\033[92m"
red="\033[91m"
endc="\033[0m"

chipset_check() {

  if [ "$(~/RH_Install-Manager/scripts/pi_model_check.sh)" == "pi_4" ]; then
    printf "\n\n\t Raspberry Pi 4 chipset found \n\n\n"
  elif [ "$(~/RH_Install-Manager/scripts/pi_model_check.sh)" == "pi_5" ]; then
    printf "\n\n\t Raspberry Pi 5 chipset found \n\n\n"
  else
    printf "\n\n\t Generic Raspberry Pi chipset found \n\n\n"

  fi

}

boot_directory_check() {

  os_version="$(~/RH_Install-Manager/scripts/os_version_check.sh)"
  if [ "$os_version" == "12" ] || [ "$os_version" == "13" ]; then

    echo "/boot/firmware"
  else
    echo "/boot"
  fi
}

ssh_enabling() {
  sudo systemctl enable ssh || return 1
  sudo systemctl start ssh || return 1
  printf "\n\n\t$green -- SSH ENABLED -- $endc\n\n\n"
  sleep 3
  return 0
}

ssh_error() {
  printf "
     $red -- SSH enabling error -- $endc

  try manually enabling using 'sudo raspi-config' later
  please: disable end re-enable SSH interface
  than reboot

  "
}

spi_enabling() {

  boot_directory=$(boot_directory_check)

  sudo raspi-config nonint do_spi 0 || return 1

  echo "
### SPI enabled - RH_Install-Manager ###

[all]
dtparam=spi=on
" | sudo tee -a "${boot_directory}"/config.txt || return 1

  if [ -e /etc/modprobe.d/raspi-blacklist.conf ]; then
    sudo sed -i 's/^blacklist spi-bcm2708/#blacklist spi-bcm2708/' /etc/modprobe.d/raspi-blacklist.conf || return 1
  fi

  printf "\n\t$green -- SPI ENABLED -- $endc\n\n\n"
  sleep 3
  return 0
}

spi_error() {
  printf "
     $red -- SPI enabling error -- $endc

  try manually enabling using 'sudo raspi-config' later
  please: disable end re-enable SPI interface
  than reboot

  "
}

i2c_enabling() {

  boot_directory=$(boot_directory_check)

  sudo raspi-config nonint do_i2c 0 || return 1

  echo "
### I2C enabled - RH_Install-Manager ###

[pi5]
dtoverlay=i2c1-pi5
dtparam=i2c_arm=on

[pi3]
dtparam=i2c_arm=on
dtparam=i2c_baudrate=75000
core_freq=250
i2c-bcm2708
i2c-dev
dtparam=i2c1=on

[all]
dtparam=i2c_arm=on
  " | sudo tee -a "${boot_directory}"/config.txt || return 1
  #    sudo sed -i 's/^blacklist i2c-bcm2708/#blacklist i2c-bcm2708/' /etc/modprobe.d/raspi-blacklist.conf || return 1

  printf "\n\t$green -- I2C ENABLED -- $endc\n\n\n"
  sleep 3
  return 0
}

i2c_error() {
  printf "
     $red -- I2C enabling error -- $endc

  try manually enabling using 'sudo raspi-config' later
  please: disable end re-enable I2C interface
  than reboot

  "
}

uart_enabling() {

  boot_directory=$(boot_directory_check)

  if [ ! -e "${boot_directory}/config.txt.dist" ]; then
    sudo cp "${boot_directory}/config.txt" "${boot_directory}/config.txt.dist" || return 1
  fi
  if [ ! -e "${boot_directory}/cmdline.txt.dist" ]; then
    sudo cp "${boot_directory}/cmdline.txt" "${boot_directory}/cmdline.txt.dist" || return 1
  fi

  sudo raspi-config nonint do_serial_hw 0
  serial_status=$?
  if [ "$serial_status" -eq 127 ]; then
    echo "Older raspi-config found - using combined UART configuration"
    sudo raspi-config nonint do_serial 2 || return 1
  elif [ "$serial_status" -ne 0 ]; then
    return 1
  else
    sudo raspi-config nonint do_serial_cons 1 || return 1
  fi

  sudo sed -i 's/console=serial0,115200//g' "${boot_directory}/cmdline.txt" || return 1
  echo "
  console serial output disabled - requires REBOOT
  "
  echo "
### UART enabled - RH_Install-Manager ###

[pi5]
dtparam=uart0=on
dtoverlay=uart0-pi5

[all]
dtoverlay=miniuart-bt
dtparam=uart0=on  #  Bookworm and newer
enable_uart=1     #  Bullseye and older
  " | sudo tee -a "${boot_directory}/config.txt" || return 1

  sleep 2

  printf "\n\t$green -- UART ENABLED -- $endc\n\n\n"
  sleep 3
  return 0
}

uart_error() {
  printf "
     $red -- UART enabling error -- $endc

  try manually enabling using 'sudo raspi-config'
  please: disable end re-enable UART interface
  than reboot

  "
}

if [ "${1}" = "ssh" ]; then
  ssh_enabling || { ssh_error; exit 1; }
fi

if [ "${1}" = "spi" ]; then
  spi_enabling || { spi_error; exit 1; }
fi

if [ "${1}" = "i2c" ]; then
  i2c_enabling || { i2c_error; exit 1; }
fi

if [ "${1}" = "uart" ]; then
  uart_enabling || { uart_error; exit 1; }
fi

reboot_message() {
  echo "

  Process completed. Please reboot Raspberry Pi now.

  "
}

if [ "${1}" = "all" ]; then
  chipset_check || echo
  ssh_enabling || { ssh_error; exit 1; }
  spi_enabling || { spi_error; exit 1; }
  i2c_enabling || { i2c_error; exit 1; }
  uart_enabling || { uart_error; exit 1; }
  echo
fi
