import os
import subprocess
import sys
from time import sleep

from modules import rhim_load_config, dots_show, internet_check, get_rhim_version, Bcolors


def self_update(config):
    internet_flag = internet_check()
    if not internet_flag:
        print(f"\t{Bcolors.RED}Looks like you don't have internet connection.{Bcolors.ENDC}")
        sleep(0.5)
        try:
            if subprocess.call(["./scripts/net_fixer.sh"]) != 0:
                print("Network repair failed. Update canceled.")
                return False
        except OSError as error:
            print("Could not run network repair: {}".format(error))
            return False
        print("Trying again...")
        internet_flag = internet_check()
    if not internet_flag:  # don't change to 'elif' - it is second check after a repair!
        print(f"\t{Bcolors.RED}Looks like you still don't have internet connection. Update canceled.{Bcolors.ENDC}")
        sleep(2)
        return False
    else:
        print(f"\t\t{Bcolors.GREEN}Internet connection - OK{Bcolors.ENDC}\n")
        sleep(1.5)
        old_version_name = get_rhim_version(True)
        print(f"\n\n\n\t Please wait: updating process from version {old_version_name}\n\n")
        dots_show(2)
        if config.beta_tester is True:
            source = 'dev'
            print("This will be the 'beta' update - may be changed in config wizard.\n")
        elif config.beta_tester is False:
            source = 'stable'
        else:
            source = config.beta_tester
        try:
            if subprocess.call(["./scripts/self_updater.sh", source]) != 0:
                print("Install-Manager update failed. Review the error above before retrying.")
                return False
        except OSError as error:
            print("Could not run Install-Manager update: {}".format(error))
            return False
        # The previous working directory now belongs to the retained backup.
        try:
            os.chdir(os.path.expanduser('~/RH_Install-Manager'))
        except OSError as error:
            print("Install-Manager files were replaced, but the installation directory could not be entered: {}".format(error))
            return False
        new_version_name = get_rhim_version(True)
        marker = '.was_updated_new' if new_version_name != old_version_name else '.was_updated_old'
        try:
            with open(os.path.expanduser('~/.rhim_markers/' + marker), 'w') as stream:
                stream.write('RHIM update completed\n')
        except OSError as error:
            print("Install-Manager files were replaced, but the update marker could not be saved: {}".format(error))
            return False
        print(f"""
        
        RotorHazard Manager updated to version {new_version_name}
        
                You can check update-notes.
    
                """)
        sleep(1)
        return True


def main():
    config = rhim_load_config()
    return 0 if self_update(config) else 1


if __name__ == "__main__":
    sys.exit(main())
