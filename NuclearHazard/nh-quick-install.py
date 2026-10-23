from rpi_update import installation
import os
import sys
from modules import write_json, load_json, name_check
from compatibility_check import main as compatibility_check


def main():
    username = name_check()
    compatibility_check()
    passed_install_step = os.getenv('INSTALL_STEP')
    if passed_install_step not in ['1', '2', 'wifi']:
        print("\n\n\tPlease specify the install step with the ./nh-install.sh command:"
              "\n\t'./nh-install.sh 1/2/wifi'\n")
        input("\n\n\tHit 'Enter' to exit and try again.\n")
        sys.exit()
    config_file = f"/home/{username}/RH_Install-Manager/NuclearHazard/nh-updater-config.json"
    config = load_json(config_file)
    config.user = username
    write_json(config, config_file)
    result = installation(True, config, False, passed_install_step)
    return 1 if result is False else 0


if __name__ == "__main__":
    sys.exit(main())
