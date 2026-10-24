#!/bin/bash

dots50() {
  for _ in {1..50}; do
    printf "."
    sleep 0.05
  done
  printf "\n\n"
}

green="\033[92m"
endc="\033[0m"
underline="\033[4m"

printf "\n\nSoftware will be automatically closed.\n"
printf "\nWord 'Killed' may be shown.\n"
printf "\nPlease wait...\n"
sleep 1.2
printf "\n\nUpdating process has been started\n\n" &
dots50
printf "\n"
for pid in $(pgrep -ax python3 | grep start_rhim.py | awk '{print $1}'); do kill -9 "$pid"; done
for pid in $(pgrep -ax python3 | grep start_rhim.py | awk '{print $1}'); do kill -9 "$pid"; done # not a mistake - last line in rhim.sh
cd "$HOME/RH_Install-Manager" || exit 1
python3 "$HOME/RH_Install-Manager/self_update.py" || {
  printf '\nUpdate failed. Review the error above before retrying.\n' >&2
  exit 1
}
cd ~ || exit 1
sleep 1.2
cd ~/RH_Install-Manager || exit 1
printf "\n\n $green Update process done, please "$underline"re-enter$endc$green ~/RH_Install-Manager directory \n"
printf "  by typing$endc 'cd ~/RH_Install-Manager'$green or just type$endc 'rhim'\n"
printf "\n\n"
printf "         -- Hit Enter to continue --"
printf "\n\n"
