import os
import sys
from time import sleep
from net_hotspot_menu import net_menu
from conf_wizard_rhim import conf_rhim
from modules import clear_the_screen, Bcolors, logo_top, triangle_image_show, rhim_asci_image_show, rhim_load_config, \
    load_rhim_sys_markers, write_rhim_sys_markers, get_rhim_version, rhim_config_check, write_json
from nodes_flash import flashing_menu
from nodes_update_old import nodes_update as old_flash_gpio
from rpi_update import main_window as rpi_update, rh_update_check


def compatibility():  # adds compatibility and fixes with previous versions
    from compatibility_check import main as prev_comp
    prev_comp()


def attribute_error_handling():
    err_msg = """
    AttributeError

    It is possible that a {underline}reboot is required{endc}
    to reload hardware interfaces.
    If this error persists, you may have a configuration mismatch.
    Check your username and other parameters of your configuration.

    You may also try to re-open this program with './rhim.sh' command.

    """.format(underline=Bcolors.UNDERLINE, endc=Bcolors.ENDC)
    print(err_msg)
    input("\n\n\tHit Enter to continue and next check your configuration.")
    clear_the_screen()


def read_aliases_file():
    aliases_to_show = []
    with open('./resources/aliases.txt', 'r') as aliases_file:
        for line in aliases_file:
            if 'alias ' in line and '###' not in line:
                line = line.replace('alias ', '')
                line = line[0:line.index('=')] + ' ' + line[line.index('#'):-1]
                line = line.replace('#', '\t\t\t')
                aliases_to_show.append(line)
            elif '#' in line and '###' not in line:
                line = line.replace('#', '')
                aliases_to_show.append(line)
            elif '###' not in line:
                aliases_to_show.append(line)

    aliases_to_show = ('\n\t\t'.join(aliases_to_show))

    return aliases_to_show


def log_to_dev(config):
    log_write(config)
    log_send(config)


def log_write(config):
    os.system(f"./scripts/log_write.sh {config.user}")


def log_send(config):
    while True:
        selection = input("\n\n\tDo you want to send a log file for a review to the developer? [y/n] ")
        if selection == 'y' or selection == 'yes':
            log_name = input("\n\tPlease enter your name: ")
            os.system(f"./scripts/log_send.sh {config.user} {log_name}")
            f = open("./log_data/log_code.txt", "r")
            code = ''
            for line in f:
                code = line
            code_error_msg = """
                -- Error occurred --

        Please send log file manually - from 'log_data' folder. 
        Uploading to server process has failed.
            """
            code_report = f"""
User code: {code}

------------------------------

"""
            print(code_report) if code != '' else print(code_error_msg)
        if selection == 'n' or selection == 'no':
            print("\n\nOK - your log file is stored as 'log.txt' in RH_Install-Manager/log_data/ directory.")
        input("\nHit 'Enter' to continue\n\n")
        if not os.system("cowsay You are awesome! Fly safe."):
            sleep(3)
        break


def rhim_recently_updated_check(config):
    updated_recently_with_new_version_flag = os.path.exists(f"/home/{config.user}/.rhim_markers/.was_updated_new")
    # true if self update was performed and new version was available to downloaded
    updated_recently_with_old_version_flag = os.path.exists(f"/home/{config.user}/.rhim_markers/.was_updated_old")
    # true if self update was performed and version was not available to downloaded
    if updated_recently_with_new_version_flag:
        clear_the_screen()
        logo_top(config.debug_mode)
        print("""\n\n {bold}

            Software was updated recently to the new version.

            You can read update notes now.


             {endc}  {green} 
                r - Read update notes {endc}{yellow}

                s - Skip and don't show again{endc}
            """.format(bold=Bcolors.BOLD_S, endc=Bcolors.ENDC,
                       green=Bcolors.GREEN, yellow=Bcolors.YELLOW))
        while True:
            selection = input()
            if selection == 'r':
                os.system("less ./docs/update-notes.txt")
                sleep(0.5)
                break
            elif selection == 's':
                break
    os.system(f"rm /home/{config.user}/.rhim_markers/.was_updated_new >/dev/null 2>&1")
    os.system(f"rm /home/{config.user}/.rhim_markers/.was_updated_old >/dev/null 2>&1")
    if updated_recently_with_new_version_flag or updated_recently_with_old_version_flag:
        os.system("rm ./.first_time_here > /dev/null 2>&1")
        return True
    else:
        return False


def rhim_update_available_check():
    # no config.user usage due to order of operations
    if os.path.exists("./.new_rhim_version_diff_file") and os.path.exists("./updater-config.json"):
        if os.path.getsize("./.new_rhim_version_diff_file"):
            rhim_update_available_flag = True
        else:
            rhim_update_available_flag = False  # done this way due to development purposes and weird edge cases
    else:
        rhim_update_available_flag = False
    return True if rhim_update_available_flag else False


def rhim_update_available_prompt(config, rhim_update_available_flag):
    if rhim_update_available_flag and config.beta_tester is False:  # don't show update prompt to beta-testers
        clear_the_screen()
        logo_top(config.debug_mode)
        print("""\n\n {bold}

                New Install-Manager version is available.

                Consider updating now (~20 secs).



             {endc}  {green} 
                    u - Update now {endc}{yellow}

                    s - Skip{endc}
            """.format(bold=Bcolors.BOLD_S, endc=Bcolors.ENDC, red=Bcolors.RED,
                       green=Bcolors.GREEN, yellow=Bcolors.YELLOW))
        while True:
            selection = input()
            if selection == 'u':
                self_updater(config)
                break
            elif selection == 's':
                break
    return True if rhim_update_available_flag else False


def welcome_screen(config):
    welcome_message = """{bold}
    Welcome! This software can install, update and manage RotorHazard.
    With supported hardware, you can also flash node firmware onto Arduinos.
    You may also enable addition features like smart-hotspot or system aliases.

    This program can also update itself - see "Features" menu.

    If you find any bugs, please report them via GitHub or Facebook.
    If you find this tool useful, please consider tipping
    using the PayPal link on the project's GitHub page.


    I wish you a good experience. Enjoy!

                                                            Pawel F.                                                
    {endc}""".format(bold=Bcolors.BOLD, red=Bcolors.RED, green=Bcolors.GREEN, endc=Bcolors.ENDC)

    first_time_flag = os.path.exists("./.first_time_here")
    while first_time_flag and not rhim_recently_updated_check(config):
        clear_the_screen()
        logo_top(config.debug_mode)
        print(welcome_message)
        selection = input(f"\n\t\t\t{Bcolors.GREEN}Open next page by typing 'n'{Bcolors.ENDC}\n\n").lower()
        if selection == 'n':
            os.system("rm ./.first_time_here")
            first_time_flag = False  # done that way so after configuration user won't be redirected back here
        if selection == 'f':  # helpful when troubleshooting, going further without changing the folder contents
            first_time_flag = False
            show_about(config)


"""
    After that you will be asked about system configuring.
    Please perform it, if you haven’t done it manually already. 
    Interfaces like: UART, SPI, I2C and SSH will be enabled. 
"""


def splash_screen(updater_version):
    clear_the_screen()
    print("\n\n")
    triangle_image_show()
    print(f"\t      {Bcolors.BOLD} RotorHazard Install Manager - version: {str(updater_version)}{Bcolors.ENDC}")
    sleep(1.5)


def serial_menu(config):
    rhim_status = load_rhim_sys_markers(config.user)

    def uart_enabling():  # UART enabling prompt is also being shown when entering nodes flash menu for the first time
        # TODO Make this repeatable without adding multiple copies at the end of config.txt.
        if os.system("./scripts/sys_conf.sh uart") != 0:
            print("UART configuration failed. Review the error before retrying.")
            return False
        rhim_status.uart_support_added = True
        if not write_rhim_sys_markers(rhim_status, config.user):
            return False
        print("""

        Serial port enabled successfully.
        A reboot is required.



        r - Reboot now{yellow}

        e - Exit{endc}
            """.format(endc=Bcolors.ENDC, yellow=Bcolors.YELLOW_S))
        selection = input()
        if selection == 'r':
            os.system("sudo reboot")
        elif selection == 'e':
            return

    while True:
        clear_the_screen()
        logo_top(config.debug_mode)
        serial_adding_menu = """
            Serial port (UART) must be enabled before Arduinos can be programmed.
            Do you want to enable it now?



         {green}y - yes, enable UART now {endc}

                s - skip this prompt

                d - don't show this prompt again

        {yellow}a - abort{endc}


            """.format(yellow=Bcolors.YELLOW_S, green=Bcolors.GREEN_S, endc=Bcolors.ENDC)
        selection = input(serial_adding_menu)
        if selection == 'y':
            if rhim_status.uart_support_added:
                print("\n\n\t\tLooks like you already enabled Serial port. \n\t\tDo you want to continue anyway?\n")
                selection = input(f"\t\t\t{Bcolors.YELLOW}Press 'y' for yes or 'a' for abort{Bcolors.ENDC}\n")
                if selection == 'y':
                    uart_enabling()
                    break
                elif selection == 'a':
                    break
            else:
                uart_enabling()
                break
        elif selection == 's':
            old_flash_gpio(config) if config.old_hw_mod else flashing_menu(config)
            break
        elif selection == 'd':
            rhim_status.uart_support_added = True
            if not write_rhim_sys_markers(rhim_status, config.user):
                return False
            old_flash_gpio(config) if config.old_hw_mod else flashing_menu(config)
            break
        elif selection == 'a':
            break


def aliases_menu(config):
    rhim_status = load_rhim_sys_markers(config.user)

    def aliases_content():
        """load rhim status, update aliases then write rhim_status"""
        os.system("cat ./resources/aliases.txt | tee -a ~/.bashrc")
        rhim_status.aliases_implemented = True
        if not write_rhim_sys_markers(rhim_status, config.user):
            return False
        print("\n\n\t\t    Aliases added successfully")
        sleep(2)
        return

    while True:
        clear_the_screen()
        aliases_description = f""" 
        Aliases in Linux act like shortcuts or references to another commands. 
        You can use them in the terminal window. 
        For example, instead of typing 'python3 ~/RotorHazard/src/server/server.py' 
        you can just type 'rh'. Aliases can be modified and added anytime 
        by opening '~./bashrc' in a text editor like 'nano'.
        After that, reboot or type 'source ~/.bashrc'. 
        {Bcolors.BOLD}
        {read_aliases_file()}
        {Bcolors.ENDC}
            Do you want to use the above aliases in your system?
            After adding, a reboot is required to enable."""
        print(aliases_description)
        selection = input(f"\n\t\t\t{Bcolors.YELLOW}Press 'y' for yes or 'a' for abort{Bcolors.ENDC}\n")
        if selection == 'y':
            if rhim_status.aliases_implemented:
                print("""

            Looks like you already have aliases added. 
            Do you want to continue anyway?

        """)
                selection = input(f"\t\t\t{Bcolors.YELLOW}Press 'y' for yes or 'a' for abort{Bcolors.ENDC}\n")
                if selection == 'y':
                    aliases_content()
                    break
                elif selection == 'a':
                    return
            else:
                aliases_content()
                break
        elif selection == 'a':
            return


def self_updater(config):
    def check_if_beta_user(config):
        if config.beta_tester is not False:
            rhim_source_name = "dev" if config.beta_tester is True else config.beta_tester
            updater_info = f'{Bcolors.RED}' \
                           f'Source of the update is set to the "{Bcolors.UNDERLINE}{Bcolors.BOLD}{rhim_source_name}' \
                           f'{Bcolors.ENDC}{Bcolors.RED}{Bcolors.BOLD}" branch.{Bcolors.ENDC}\n'
        else:
            updater_info = ''

        return updater_info

    while True:
        clear_the_screen()
        logo_top(config.debug_mode)
        updater = """
        Update Install Manager by hitting '{green}u{endc}' now. This is advised 
        before updating the RotorHazard server or flashing nodes.

        Manager version number is related to the {red}latest supported RotorHazard 
        stable server version{endc} and {blue}nodes firmware API number{endc} that it contains.
        For example, version 6a.{red}401{endc}{bold}.{blue}35{endc} supports RotorHazard 4.0.1 stable 
        and contains nodes firmware with "API level 35".

        Self-updater will test your internet connection before every update
        and prevent update if there is no internet connection established.

        {underline}Version of this program installed right now{endc}{bold}: {version}

        {updater_info}

            {green_s}u - Update Install-Manager now{endc}

           {yellow}e - Exit to main menu{endc}
        """.format(green=Bcolors.GREEN, green_s=Bcolors.GREEN_S, endc=Bcolors.ENDC, bold=Bcolors.BOLD,
                   underline=Bcolors.UNDERLINE, blue=Bcolors.BLUE, version=get_rhim_version(False),
                   yellow=Bcolors.YELLOW_S, red=Bcolors.RED, updater_info=check_if_beta_user(config))
        print(updater)
        selection = input()
        if selection == 'e':
            break
        elif selection in ['u', 'dev', 'stab']:
            if selection == 'dev':
                config.beta_tester = True
            elif selection == 'stab':
                config.beta_tester = False
            write_json(config, f"/home/{config.user}/RH_Install-Manager/updater-config.json")
            os.system("scripts/updater_from_rhim.sh")


def features_menu(config):
    while True:
        clear_the_screen()
        logo_top(config.debug_mode)
        update_available = Bcolors.UNDERLINE if rhim_update_available_check() else ''
        features_menu_content = """
        
                            {rmf}FEATURES MENU{endc}{bold}


                    1 - {update_flag}Update the Install-Manager{endc}{bold}

                    2 - Access Point and Internet

                    3 - Show actual Pi's GPIO

                    4 - Add useful aliases

                    5 - Create a RHIM log file{yellow}

                    e - Exit to main menu {endc}

                 """.format(bold=Bcolors.BOLD_S, underline=Bcolors.UNDERLINE, endc=Bcolors.ENDC,
                            update_flag=update_available,
                            blue=Bcolors.BLUE, yellow=Bcolors.YELLOW_S, red=Bcolors.RED_S, rmf=Bcolors.RED_MENU_HEADER)
        print(features_menu_content)
        selection = input()
        if selection == '1':
            self_updater(config)
        elif selection == '2':
            net_menu(config)
        elif selection == '3':
            clear_the_screen()
            os.system("pinout")
            input("\nDone? Hit 'Enter'\n")
        elif selection == '4':
            try:
                aliases_menu(config)
            except AttributeError:
                attribute_error_handling()
        elif selection == '5':
            log_to_dev(config)
        elif selection == 'e':
            break


def show_about(config):
    while config.user != "NuclearHazard":
        clear_the_screen()
        welcome_first_page = """{bold}  

    Please configure Manager software using a wizard after reading this page.


    This wizard will configure Install Manager, not RotorHazard itself.



    RotorHazard server versions that may be selected:

    > {blue}'stable'{endc}{bold} - full stable release tested and suitable for live events{endc}{bold}

    > {blue}'beta'  {endc}{bold} - contains new features but may also contain some bugs{endc}{bold}

    > {blue}'main'{endc}{bold}   - current development version with highest risk of errors{endc} 



    {green}c - Enter configuration wizard{endc}{yellow}

           e - Exit to menu {endc}

        """.format(green=Bcolors.GREEN_S, blue=Bcolors.BLUE, endc=Bcolors.ENDC,
                   yellow=Bcolors.YELLOW_S, bold=Bcolors.BOLD)
        print(welcome_first_page)
        selection = input()
        if selection == 'c':
            config = conf_rhim(config)
            break
        elif selection == 'e':
            break

    return config


def end():
    clear_the_screen()
    print("\n\n")
    rhim_asci_image_show()
    print(f"\t\t\t{Bcolors.BOLD}Happy flyin'!{Bcolors.ENDC}\n")
    sleep(1.5)
    clear_the_screen()
    sys.exit()


def main_menu(config):
    while True:
        clear_the_screen()
        logo_top(config.debug_mode)
        rhim_config = load_rhim_sys_markers(config.user)
        rh_installation_state = f"{Bcolors.BLUE}1 - RotorHazard Manager{Bcolors.ENDC}"
        if not rhim_config_check():  # checks is RH configured
            conf_color = Bcolors.GREEN
            conf_arrow = "  <- go here first"
        else:
            conf_color, conf_arrow = '', ''
            if not rhim_config.first_part_of_install and not rhim_config.second_part_of_install:
                rh_installation_state = f"{Bcolors.GREEN}1 - RotorHazard Manager{Bcolors.ENDC}{Bcolors.RED}  <- go here now{Bcolors.ENDC}"
            elif rhim_config.first_part_of_install and not rhim_config.second_part_of_install:
                rh_installation_state = f"{Bcolors.GREEN}1 - RotorHazard Manager{Bcolors.ENDC}{Bcolors.RED}  <- continue{Bcolors.ENDC}"
            if rhim_config.first_part_of_install and rhim_config.second_part_of_install and rh_update_check(
                    config):  # checks is RH is about to be updated
                rh_installation_state = f"{Bcolors.GREEN}1 - RotorHazard Manager{Bcolors.ENDC}{Bcolors.RED} ! PENDING STABLE UPDATE !{Bcolors.ENDC}"

        main_menu_content = """ 
        
                            {rmf}MAIN MENU{endc}

                        {bold}  
                    {install_state} 
                        {endc}{bold}
                    2 - Nodes flash and update {endc}{bold}

                    3 - Additional features{config_color}

                    4 - Configuration Wizard{config_arrow}{endc}{bold}{yellow}

                    e - Exit to Raspberry OS{endc}

                """.format(bold=Bcolors.BOLD_S, underline=Bcolors.UNDERLINE, endc=Bcolors.ENDC, green=Bcolors.GREEN,
                           blue=Bcolors.BLUE, yellow=Bcolors.YELLOW_S, red=Bcolors.RED, config_color=conf_color,
                           rmf=Bcolors.RED_MENU_HEADER, config_arrow=conf_arrow, install_state=rh_installation_state)
        print(main_menu_content)
        selection = input()
        if selection == '1':
            if rhim_config_check():
                try:
                    rpi_update(config)
                except AttributeError:
                    attribute_error_handling()
            else:
                clear_the_screen()
                logo_top(config.debug_mode)
                print("\n\n\t\tPlease enter Configuration Wizard first."
                      "\n\n\t\tHit 'Enter' now to go back.\n\n\n")
                input()
        elif selection == '2':
            def stm_flashing_confirmed():
                clear_the_screen()
                logo_top(config.debug_mode)
                print("\n\n    Please note that this part of the menu only applies to Arduino based PCBs."
                      "\n\n    Flashing STM32 based boards (e.g. NuclearHazard) is done via RH web GUI."
                      "\n\n\n\n\tHit 'Enter' to confirm\n\n\n")
                input()
                return True

            while stm_flashing_confirmed():
                try:
                    rhim_status = load_rhim_sys_markers(config.user)
                    if rhim_status.uart_support_added:
                        old_flash_gpio(config) if config.old_hw_mod else flashing_menu(config)
                        break
                    # enters "old" flashing menu only when "old_hw_mod" is confirmed
                    else:
                        serial_menu(config)
                        break
                except AttributeError:
                    attribute_error_handling()
                    break
        elif selection == '3':
            features_menu(config)
        elif selection == '4':
            config = show_about(config)
        elif selection == 'e':
            end()


def main():
    compatibility()
    updater_version = get_rhim_version(False)
    config = rhim_load_config()
    splash_screen(updater_version)
    rhim_recently_updated_check(config)
    rhim_update_available_prompt(config, rhim_update_available_check())
    welcome_screen(config)
    main_menu(config)


if __name__ == "__main__":
    main()
