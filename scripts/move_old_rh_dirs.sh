#!/bin/bash

upgradeDate="$(date +%Y%m%d%H%M)" || exit 1
for source in "/home/${1}/RotorHazard" /home/"${1}"/RotorHazard-*; do
  if [ -d "$source" ] || [ -L "$source" ]; then
    source_name="${source##*/}"
    destination="/home/${1}/${source_name/RotorHazard-/RotorHazard_}_${upgradeDate}"
    if [ -e "$destination" ] || [ -L "$destination" ]; then
      echo "Cannot preserve $source: backup already exists at $destination. Move it to a safe location before retrying." >&2
      exit 1
    fi
    mv -T -- "$source" "$destination" || { echo "Could not preserve $source" >&2; exit 1; }
  fi
done
exit 0
