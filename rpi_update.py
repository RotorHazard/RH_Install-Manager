import glob
import os
import sys
from shlex import quote
from runtime_preflight import check_runtime
from source_safety import locked_operation, config_path, apply_config_file, cleanup_old, read_state, check_activation
from pathlib import Path
from time import sleep
from conf_wizard_rh import conf_rh
from modules import clear_the_screen, Bcolors, internet_check, load_rhim_sys_markers, \
    write_rhim_sys_markers, rhim_load_config, server_start, logo_top, write_json, rhim_config_check


def check_preferred_rh_version(config):
    with open(f"/home/{config.user}/RH_Install-Manager/version.txt", "r") as file:
        lines = file.readlines()
        line_number = 0

        for line in lines:
            line_number += 1
            if line_number == 1:
                stable_name_line = line.strip()
            if line_number == 3:
                beta_name_line = line.strip()
                break

    no_dots_preferred_rh_version = stable_name_line.split(".")[1].strip()
    converted_rh_version_name = \
        no_dots_preferred_rh_version[0] + "." + no_dots_preferred_rh_version[1] + "." + no_dots_preferred_rh_version[2:]

    stable_release_name = str(
        "v" + converted_rh_version_name)  # stable rh target is being loaded from the version.txt file

    beta_release_name = str("v" + beta_name_line)

    if config.rh_version == 'stable':
        server_version = stable_release_name
    elif config.rh_version == 'beta':
        server_version = beta_release_name
    elif config.rh_version == 'master' or config.rh_version == 'main':
        server_version = 'main'
    else:  # in case of 'custom' version selected in wizard
        server_version = config.rh_version

    return server_version, no_dots_preferred_rh_version, stable_release_name


# TODO I would like to move th tags out of being hard-coded here.
# Maybe get a list of tags and ask user to select from list
# or automatically figure out the newest non-beta tag?


def get_rotorhazard_server_version(config):
    server_py = Path(f"/home/{config.user}/RotorHazard/src/server/server.py")
    server_installed_flag = False
    non_stable_flag = False
    if server_py.exists():
        with open(server_py, 'r') as open_file:
            for line in open_file:
                if line.startswith('RELEASE_VERSION'):
                    # RELEASE_VERSION = "2.2.0 (dev 1)" # Public release version code
                    current_server_version_name = line.strip().split('=')[1].strip()
                    current_server_version_name = current_server_version_name.split('#')[0].replace('"', '').strip()
                    server_installed_flag = True
                    non_stable_flag = True if 'dev' in line or 'beta' in line else False
                    break
    else:
        current_server_version_name = '0'  # string so string operations like .split can be performed
        server_installed_flag = False
    return server_installed_flag, current_server_version_name, non_stable_flag


def rh_update_check(config):
    raw_installed_rh_server = get_rotorhazard_server_version(config)[1]  # 3.0.0-dev2
    installed_rh_server = raw_installed_rh_server.split("-")[0]  # 3.0.0
    installed_rh_server_number = int(installed_rh_server.replace(".", ""))  # 300
    server_installed_flag = get_rotorhazard_server_version(config)[0]  # check if RH is installed
    non_stable_source = get_rotorhazard_server_version(config)[2]
    newest_possible_rh_version = int(
        check_preferred_rh_version(config)[1])  # derived from Install-Manager version name 232.25.3h -> 232
    if installed_rh_server_number < newest_possible_rh_version and server_installed_flag:
        rh_update_available_flag = True
    else:
        rh_update_available_flag = False
    if installed_rh_server_number == newest_possible_rh_version and server_installed_flag and non_stable_source:
        rh_update_available_flag = True
    if rh_update_available_flag:
        return True
    else:
        return False


def check_rotorhazard_config_status(config):
    try:
        path = config_path("/home/" + config.user)
    except (OSError, ValueError) as error:
        return "Data path unresolved: " + str(error), False
    if os.path.exists(path):
        config_soft = f"{Bcolors.GREEN}-> configured{Bcolors.ENDC} 👍"
        config_flag = True
    else:
        config_soft = f"{Bcolors.YELLOW}-> {Bcolors.UNDERLINE}not configured{Bcolors.ENDC} 👎"
        config_flag = False
    return config_soft, config_flag


def show_update_completed():
    update_completed = """\n\n
        #################################################
        ##                                             ##
        ##{bold}{green}Update completed! {thumbs}{endc}##
        ##                                             ##
        #################################################
                """.format(thumbs="👍👍👍  ", bold=Bcolors.BOLD_S,
                           endc=Bcolors.ENDC_S, green=Bcolors.GREEN_S)
    return update_completed


def end_update(config, server_configured_flag, server_installed_flag):
    if not server_configured_flag and server_installed_flag:
        configure = f"{Bcolors.GREEN}c - Configure RotorHazard now{Bcolors.ENDC}"
    else:
        configure = "c - Reconfigure RotorHazard server"
    while True:
        print(show_update_completed())
        clearing_color = ''
        old_installations_were_found = False
        old_rh_directories_found = glob.glob('.././RotorHazard_*')
        if old_rh_directories_found:
            clearing_color = Bcolors.GREEN
            old_installations_were_found = True
        print(f"""
                {configure}

                r - Reboot - recommended before using the timer

                s - Start RotorHazard server now {clearing_color}

                o - Review retained RotorHazard backups{Bcolors.YELLOW}

                e - Exit now{Bcolors.ENDC}""")
        selection = completion_input()
        if selection == 'r':
            if os.system("sudo reboot") != 0:
                show_runtime_error("Reboot failed. Reboot the host manually before using the timer.")
                return False
        elif selection == 's':
            os.chdir(f"/home/{config.user}/RH_Install-Manager")
            if not server_configured_flag:
                print("RotorHazard is installed. Configuration is pending; configure it before starting.")
                continue
            if not server_start():
                return False
        elif selection == 'o':
            try:
                cleanup_old("/home/" + config.user)
            except (OSError, ValueError) as error:
                show_runtime_error("Cleanup refused: " + str(error))
                return False
            completion_input("Press Enter after reviewing retained paths.")
            clear_the_screen()
        elif selection == 'c':
            try:
                if conf_rh() is False:
                    return False
            except EOFError:
                print("RotorHazard is installed. Configuration is pending.")
                return True
            server_configured_flag = check_rotorhazard_config_status(config)[1]
        elif selection == 'e':
            return True


def end_normal_installation():
    while True:
        print(f"""

                r - Reboot without configuration 
                {Bcolors.GREEN}
                c - {Bcolors.UNDERLINE}Configure RotorHazard server now{Bcolors.ENDC}

                e - Exit now""")

        selection = completion_input()
        if selection == 'r':
            if os.system("sudo reboot") != 0:
                show_runtime_error("Reboot failed. Reboot the host manually before using the timer.")
                return False
        elif selection == 'c':
            try:
                if conf_rh() is False:
                    return False
            except EOFError:
                print("RotorHazard is installed. Configuration is pending.")
            break
        elif selection == 'e':
            return True
    return True


def end_quick_installation(config):
    rhim_prompt = (f"""{Bcolors.GREEN}\n
        If you want to adjust any additional features like LEDs etc.
        please open Install-Manager by typing '{Bcolors.ENDC}rhim{Bcolors.GREEN}'. {Bcolors.ENDC}\n\n""")
    try:
        apply_config_file("/home/" + config.user,
                          "/home/{}/RH_Install-Manager/NuclearHazard/nh-rh-config.json".format(config.user))
    except (OSError, ValueError) as error:
        show_runtime_error("Could not apply NuclearHazard server configuration: " + str(error))
        return False
    if os.system("cp ~/RH_Install-Manager/NuclearHazard/nh-updater-config.json ~/RH_Install-Manager/updater-config.json") != 0:
        show_runtime_error("Could not apply NuclearHazard installer configuration. Retry configuration.")
        return False
    print("\t\tDefault NuclearHazard configuration applied.\n\n")
    sleep(2)
    selection = completion_input(f"""{Bcolors.GREEN}
        Do you want to activate automatic NuclearHazard Wi-Fi? [y/N]
        You can do it later by typing '{Bcolors.ENDC}./nh-install.sh wifi{Bcolors.GREEN}'
        in the directory {Bcolors.ENDC}~/RH_Install-Manager/NuclearHazard\n\n\t""")
    if selection == 'y':
        if os.system("sh ~/RH_Install-Manager/NuclearHazard/nh-wifi.sh") != 0:
            show_runtime_error("NuclearHazard Wi-Fi configuration failed. Review the error before retrying.")
            return False
        print(rhim_prompt)
    else:
        print(rhim_prompt)
    return True


def end_of_part_1():
    while True:
        print(f"""
            {Bcolors.GREEN}
               r - Reboot now {Bcolors.ENDC}

               e - Exit now""")

        selection = completion_input()
        if selection == 'r':
            if os.system("sudo reboot") != 0:
                show_runtime_error("Reboot failed. Reboot the host manually before continuing with part 2.")
                return False
        elif selection == 'e':
            return


def completion_input(prompt=""):
    try:
        return input(prompt)
    except EOFError:
        return 'e'


def show_runtime_error(message):
    print(message)
    try:
        input("\nPress Enter to return.")
    except EOFError:
        pass


def show_runtime_result(runtime):
    print("Python {}.{} - OK".format(*runtime["version"][:2]))
    if runtime["create_venv"]:
        print("Virtual environment will be created during installation.")
    else:
        print("Virtual environment - OK")


def run_runtime_script(user, target, git_flag, stage, runtime):
    script = {"part1": "install_rh_part_1.sh", "part2": "install_rh_part_2.sh",
              "update": "update_rh.sh"}[stage]
    executable = runtime["base_python"] if stage == "part1" else runtime["python"]
    args = ["/home/{}/RH_Install-Manager/scripts/{}".format(user, script),
            user, target, str(git_flag or ""), executable]
    if runtime["unknown_target"]:
        args.append("--accept-unknown")
    if os.system(" ".join(quote(arg) for arg in args)) != 0:
        show_runtime_error("Operation failed. Files or dependencies may have changed, and RotorHazard may be stopped. Review the error before retrying.")
        return False
    return True


@locked_operation
def installation(conf_allowed, config, git_flag, quick_install=False, restart=False):
    def first_part_of_installation_done_check(config):
        rhim_config = load_rhim_sys_markers(config.user)
        return True if rhim_config.first_part_of_install else False

    first_part_completed_short = """


            ######################################################
            ##                                                  ##
            ##{bold}{green} First part completed  {thumbs}{endc}##
            ##                                                  ##
            ######################################################

            {green_no_s}
            Please reboot now and connect to the timer again. 
            Afterward, type the command from the instructions: 
            '{endc_no_s}~/RH_Install-Manager/NuclearHazard/nh-install.sh 2{green_no_s}' 

            You can also exit now and type: '{endc_no_s}source ~/.bashrc{green_no_s}'. 
            Then immediately proceed with the installation,
            by typing '{endc_no_s}./nh-install.sh 2{green_no_s}'. Reboot later. 
                        """.format(thumbs="👍👍👍  ", bold=Bcolors.BOLD_S, green_no_s=Bcolors.GREEN,
                                   endc_no_s=Bcolors.ENDC, endc=Bcolors.ENDC_S, green=Bcolors.GREEN_S)

    first_part_completed_long = """


            ######################################################
            ##                                                  ##
            ##{bold}{green} First part completed  {thumbs}{endc}##
            ##                                                  ##
            ######################################################

            {green_no_s}
            Please reboot now and connect to the timer again. 
            Afterward, reopen Install-Manager by typing '{endc_no_s}rhim{green_no_s}' 
            in the terminal window and navigate to the first item 
            in the Main Menu. 
            
            You can also exit Install-Manager now and manually type 
            '{endc_no_s}source ~/.bashrc{endc_no_s}'. {green_no_s}Then launch it again by typing '{endc_no_s}rhim{green_no_s}' 
            and continue installation. Reboot later. 
                        """.format(thumbs="👍👍👍  ", bold=Bcolors.BOLD_S, green_no_s=Bcolors.GREEN,
                                   endc_no_s=Bcolors.ENDC, endc=Bcolors.ENDC_S, green=Bcolors.GREEN_S)
    installation_completed_short = """


            ######################################################
            ##                                                  ##
            ##{bold}{green}Installation completed {thumbs}{endc}##
            ##                                                  ##
            ######################################################


                        """.format(thumbs="👍👍👍  ", bold=Bcolors.BOLD_S, green_no_s=Bcolors.GREEN,
                                   endc_no_s=Bcolors.ENDC, endc=Bcolors.ENDC_S, green=Bcolors.GREEN_S)
    installation_completed_long = """


            ######################################################
            ##                                                  ##
            ##{bold}{green}Installation completed {thumbs}{endc}##
            ##                                                  ##
            ######################################################

            {green_no_s}
            You can configure your RotorHazard installation now. 
            After doing that, please reboot the timer. 
            Some features (like UART) require this to work properly. 
            RotorHazard is installed; configuration is pending.
            You can also launch Install-Manager (type '{endc_no_s}rhim{green_no_s}')
            and check available options - after rebooting.{endc}
                        """.format(thumbs="👍👍👍  ", bold=Bcolors.BOLD_S, green_no_s=Bcolors.GREEN,
                                   endc_no_s=Bcolors.ENDC, endc=Bcolors.ENDC_S, green=Bcolors.GREEN_S)
    rhim_config = load_rhim_sys_markers(config.user)
    clear_the_screen()
    internet_flag = internet_check()
    first_part_of_installation_done_flag = first_part_of_installation_done_check(config)
    quick_install = int(quick_install)
    if quick_install != 0:
        if quick_install == 1:
            first_part_of_installation_done_flag = False
        else:
            first_part_of_installation_done_flag = True
    if restart:
        first_part_of_installation_done_flag = False
    if not internet_flag:
        print(f"\n\t{Bcolors.RED}No internet connection found. Installation canceled.{Bcolors.ENDC}")
        sleep(2)
        return False
    else:
        stage = "part2" if first_part_of_installation_done_flag else "part1"
        print("\nChecking RotorHazard environment...")
        try:
            pending = read_state("/home/" + config.user)
            if pending:
                if pending["stage"] != stage:
                    raise ValueError("Recovery is pending. Retry {} for {} first.".format(pending["stage"], pending["target"]))
                target = pending["target"]
                print("Resuming pending {} to {}.".format(stage, target))
                check_activation("/home/" + config.user, pending)
            else:
                target = check_preferred_rh_version(config)[0]
            runtime = check_runtime(config.user, target, stage, confirm=input)
        except ValueError as error:
            show_runtime_error("Installation not started: " + str(error))
            return False
        show_runtime_result(runtime)
        if not first_part_of_installation_done_flag:
            if not run_runtime_script(config.user, target, git_flag, "part1", runtime):
                return False
            if quick_install == 1:
                if os.system("~/RH_Install-Manager/scripts/additional_sys_conf.sh shutdown_pin 19 2500") != 0:
                    show_runtime_error("Shutdown pin configuration failed. Review the error before retrying.")
                    return False
                if os.system("~/RH_Install-Manager/scripts/additional_sys_conf.sh led") != 0:
                    show_runtime_error("LED configuration failed. Review the error before retrying.")
                    return False
            print(f"\n\t\t{Bcolors.GREEN}Internet connection - OK{Bcolors.ENDC}")
            sleep(1)
            clear_the_screen()
            print(f"\n\n\t{Bcolors.BOLD}Installation process has been started - please wait...{Bcolors.ENDC}")
            print(f"\n\n\t{Bcolors.BOLD}(please don't interrupt - it may take some time){Bcolors.ENDC}\n\n\n")
            if conf_allowed:
                if not config.debug_mode:
                    status = os.system(f"/home/{config.user}/RH_Install-Manager/scripts/sys_conf.sh all")
                else:
                    status = os.system(f"/home/{config.user}/RH_Install-Manager/scripts/sys_conf.sh ssh")
                    print("\n\nsimulation mode - SPI, I2C and UART won't be configured\n\n\n")
                    sleep(2)
                if status != 0:
                    show_runtime_error("Host configuration failed. No completion was recorded. Review the error before retrying.")
                    return False
            # UART enabling added here so user won't have to reboot Pi again after doing it in Features Menu
            rhim_config.first_part_of_install = True
            rhim_config.second_part_of_install = False
            if conf_allowed and not config.debug_mode:
                rhim_config.uart_support_added = True
                rhim_config.sys_config_done = True
            rhim_config.fresh_install_pending = runtime["fresh_install"]
            if not write_rhim_sys_markers(rhim_config, config.user):
                return False
            if not quick_install and os.system(
                    f"""echo "cat /home/{config.user}/RH_Install-Manager/resources/shell_hello_1.txt" >> ~/.bashrc""") != 0:
                show_runtime_error("Installation stage completed, but the shell greeting could not be saved. Continue with part 2 after reboot.")
                return False
            completion_input("\n\n\npress Enter to continue")
            clear_the_screen()
            print(first_part_completed_long) if not quick_install else print(first_part_completed_short)
            return end_of_part_1() is not False
        else:
            print(f"\n\t\t{Bcolors.GREEN}Internet connection - OK{Bcolors.ENDC}")
            sleep(2)
            clear_the_screen()
            print(
                f"\n\n\t{Bcolors.BOLD}Second part of installation has been started - please wait...{Bcolors.ENDC}")
            print(f"\n\n\t{Bcolors.BOLD}(please don't interrupt - it may take some time){Bcolors.ENDC}\n\n\n")
            if not run_runtime_script(config.user, target, git_flag, "part2", runtime):
                return False
            rhim_config.second_part_of_install = True
            rhim_config.fresh_install_pending = False
            if not write_rhim_sys_markers(rhim_config, config.user):
                return False
            completion_input("\n\n\npress Enter to continue")
            clear_the_screen()
            if quick_install:
                if not end_quick_installation(config):
                    return False
                print(installation_completed_short)
                return True
            print(installation_completed_long)
            return end_normal_installation()


@locked_operation
def update(config, git_flag):
    clear_the_screen()
    internet_flag = internet_check()
    if not internet_flag:
        print(f"\n\t{Bcolors.RED}No internet connection found. Update canceled.{Bcolors.ENDC}")
        sleep(2)
        return False
    else:
        print(f"\n\t\t{Bcolors.GREEN}Internet connection - OK{Bcolors.ENDC}")
        sleep(2)
        if not os.path.exists(f"/home/{config.user}/RotorHazard") and not read_state("/home/" + config.user):
            print(f"""{Bcolors.BOLD}

    No RotorHazard server installation found. 

    Please install your server software first.{Bcolors.ENDC}{Bcolors.GREEN} 


        i - Install the software - recommended{Bcolors.ENDC}

        a - Abort 

                    """)
            selection = input()
            if selection == 'i':
                conf_allowed = True
                return installation(conf_allowed, config, "")
            elif selection == 'igit':
                conf_allowed = True
                return installation(conf_allowed, config, "git")
            elif selection == 'a':
                clear_the_screen()
                return
            else:
                return
        else:
            try:
                pending = read_state("/home/" + config.user)
                if pending and pending["stage"] != "update":
                    raise ValueError("Recovery is pending. Retry {} for {} first.".format(pending["stage"], pending["target"]))
            except ValueError as error:
                show_runtime_error("RH update not started: " + str(error))
                return False
            change_update_to_stable = False
            preferred_rh_version = pending["target"] if pending else check_preferred_rh_version(config)[0]
            if pending:
                print("Resuming pending update to {}.".format(preferred_rh_version))
            elif rh_update_check(config) is True and config.rh_version != 'stable':
                clear_the_screen()
                confirm_stable_update_screen = """{bold}

            Looks like there is the stable update available, 
            newer than currently installed version.{endc}

            For now, you have selected {yellow}{underline}{previous_rh_source}{endc} as an update source.
            Would you like to switch to the stable version for this update?  



        {green}y - Yes, switch to stable update and proceed {endc}

               n - No, just update with existing update source

               a - Abort both and go back {endc}
                               """.format(bold=Bcolors.BOLD, endc=Bcolors.ENDC, underline=Bcolors.UNDERLINE,
                                          yellow=Bcolors.YELLOW, green=Bcolors.GREEN_S,
                                          previous_rh_source=check_preferred_rh_version(config)[0])
                print(confirm_stable_update_screen)
                selection = input()
                if selection in ['y', 'Y', '', 'ygit']:
                    change_update_to_stable = True
                elif selection == 'n':
                    change_update_to_stable = False
                elif selection == 'a':
                    return
                if not change_update_to_stable:
                    preferred_rh_version = check_preferred_rh_version(config)[0]
                else:
                    preferred_rh_version = check_preferred_rh_version(config)[2]
            print("\nChecking RotorHazard environment...")
            try:
                if pending:
                    check_activation("/home/" + config.user, pending)
                runtime = check_runtime(config.user, preferred_rh_version, "update", confirm=input)
            except ValueError as error:
                show_runtime_error("RH update not started: " + str(error))
                return False
            clear_the_screen()
            show_runtime_result(runtime)
            print(f"\n\n\t{Bcolors.BOLD}Updating existing installation - please wait...{Bcolors.ENDC}")
            print(f"\n\n\t{Bcolors.BOLD}(please don't interrupt - it may take some time){Bcolors.ENDC}\n\n\n")
            if not run_runtime_script(config.user, preferred_rh_version, git_flag, "update", runtime):
                return False
            config_soft, config_flag = check_rotorhazard_config_status(config)
            server_installed_flag, server_version_name, _ = get_rotorhazard_server_version(config)
            return end_update(config, config_flag, server_installed_flag)


def origin_change(config):
    def ask_custom_rh_version():
        while True:
            version = input("\nPlease enter the version tag that you wish to install [e.g. 2.1.0-beta.3]:\n")
            custom_confirm = input(f"""
                You entered version: '{version}' 

                Confirm [Y/n]       """)
            if custom_confirm.lower() == 'y' or not custom_confirm:
                return version

    home_dir = str(Path.home())
    clear_the_screen()
    logo_top(config.debug_mode)
    while True:
        version = input(f""" {Bcolors.BOLD}
        Choose the RotorHazard version that you want to be set
        as a origin of the download: {Bcolors.ENDC}
            
            
                s - stable
                b - beta 
                m - main
                c - custom
                
                a - abort\n\n\t""").lower()
        if version[0] == 's':
            config.rh_version = 'stable'
            break
        elif version[0] == 'b':
            config.rh_version = 'beta'
            break
        elif version[0] == 'm':
            config.rh_version = 'main'
            break
        elif version == 'c':
            # custom - hidden option, just for developers and testing.
            # Nodes flashing will be defaulted to stable in that case
            # If the user specifies custom for version, re-ask the question
            # and ask exactly what version tag they want:
            config.rh_version = ask_custom_rh_version()
            break
        elif version[0] == 'a':
            break
        else:
            print("\n\n\t\tPlease enter the correct value!")
            sleep(2)
            clear_the_screen()
            logo_top(config.debug_mode)
    write_json(config, f"{home_dir}/RH_Install-Manager/updater-config.json")
    print(f"\n\n\tOrigin changed to {Bcolors.UNDERLINE}{config.rh_version}{Bcolors.ENDC}") if version != 'a' \
        else print(f"\n\n\t{Bcolors.UNDERLINE}Configuration unchanged{Bcolors.ENDC}")
    sleep(2)


def main_window(config):
    def system_already_configured_prompt():
        clear_the_screen()
        already_configured_prompt = """{bold}

           Looks like your system is already configured.

           Consider performing installation without system config
           or update existing installation from the previous menu.{endc} 




        {green}i - Force installation without system config {endc}

               c - Force installation and system config 

               a - Abort both, go to the Main Menu
               """.format(bold=Bcolors.BOLD, endc=Bcolors.ENDC, underline=Bcolors.UNDERLINE,
                          yellow=Bcolors.YELLOW, green=Bcolors.GREEN_S)
        print(already_configured_prompt)

    while True:
        rh_config_text, rh_config_flag = check_rotorhazard_config_status(config)
        clear_the_screen()
        server_installed_flag, server_version_name, _ = get_rotorhazard_server_version(config)
        if server_installed_flag:
            colored_server_version_name = f"{Bcolors.GREEN}{server_version_name}{Bcolors.ENDC}"
        else:
            colored_server_version_name = f'{Bcolors.YELLOW}{Bcolors.UNDERLINE}not found{Bcolors.ENDC}'
        update_prompt = f"{Bcolors.RED}! PENDING STABLE UPDATE !{Bcolors.ENDC}" if rh_update_check(config) else ''
        rhim_config = load_rhim_sys_markers(config.user)
        sys_configured_flag = rhim_config.sys_config_done
        configured_server_target = check_preferred_rh_version(config)[0]
        change_option = "('d' - to change)" if rhim_config_check() else ""
        sleep(0.1)
        welcome_text = """
        \n\n{red} {bold}
        AUTOMATIC UPDATE AND INSTALLATION OF ROTORHAZARD RACING TIMER SOFTWARE
            {endc}{bold}
        You can automatically install and update RotorHazard timing software. 
        Additional dependencies and libraries also will be installed or updated.
        Current database, configs and custom bitmaps will stay on their place.

        Please update this (Manager) software, before updating RotorHazard.

        Server version currently installed: {server} {bold}{config_soft} 

        {update_prompt}
        {bold}
        You can change below configuration in Configuration Wizard in Main Menu:

        Download origin is set to the version: {endc}{underline}{blue}{server_version}{endc}   {change_option}

            """.format(bold=Bcolors.BOLD, underline=Bcolors.UNDERLINE, endc=Bcolors.ENDC, blue=Bcolors.BLUE,
                       yellow=Bcolors.YELLOW, red=Bcolors.RED, orange=Bcolors.ORANGE, change_option=change_option,
                       server_version=configured_server_target, config_soft=rh_config_text,
                       server=colored_server_version_name, update_prompt=update_prompt)
        print(welcome_text)
        if not rh_config_flag and server_installed_flag:
            configure = f"{Bcolors.GREEN}c - Configure RotorHazard server{Bcolors.ENDC}{Bcolors.RED} <- go here now{Bcolors.ENDC}"
        elif not rh_config_flag and not server_installed_flag:
            configure = "c - Reconfigure RotorHazard server"
        else:
            configure = "c - Configure RotorHazard server"
        if rh_update_check(config):
            update_text = f"{Bcolors.GREEN}u - {Bcolors.UNDERLINE}Update existing installation{Bcolors.ENDC}"
        else:
            update_text = "u - Update existing installation"
        if not rhim_config.second_part_of_install:
            if not rhim_config.first_part_of_install:
                install = f"{Bcolors.GREEN}i - {Bcolors.UNDERLINE}Install RotorHazard server{Bcolors.ENDC}{Bcolors.RED} <- go here now{Bcolors.ENDC}"
            else:
                install = f"{Bcolors.GREEN}i - {Bcolors.UNDERLINE}Continue RotorHazard server installation{Bcolors.ENDC}{Bcolors.RED} <- go here now{Bcolors.ENDC}"
        else:
            install = "i - Install RotorHazard server"
        print("""
                    {install}

                    {configure}

                    {update} 

                    s - Start RotorHazard server now{yellow}

                    e - Exit to Main Menu{endc}

                """.format(yellow=Bcolors.YELLOW, endc=Bcolors.ENDC, configure=configure, install=install,
                           update=update_text))
        selection = input()
        if selection == 'c':
            if server_installed_flag:
                conf_rh()
            else:
                print("Please install RH server before configuring.")
                sleep(2)
        elif selection == 's':
            if server_installed_flag:
                server_start()
            else:
                print("Please install the RotorHazard server first")
                sleep(2)
        elif selection == 'i' or selection == 'igit':
            # rh_found_flag = os.path.exists(f"/home/{config.user}/RotorHazard")
            if sys_configured_flag and not (rhim_config.first_part_of_install and not rhim_config.second_part_of_install):
                system_already_configured_prompt()
                selection = input()
                if selection == 'i':
                    conf_allowed = False
                    installation(conf_allowed, config, "")
                elif selection == 'igit':
                    conf_allowed = False
                    installation(conf_allowed, config, "git")
                elif selection == 'c':
                    confirm_valid_options = ['y', 'yes', 'n', 'no', 'abort', 'a']
                    while True:
                        confirm = input("\n\t\tAre you sure? [yes/abort]\t").strip()
                        if confirm in confirm_valid_options:
                            break
                        else:
                            print("\nPlease type the correct answer")
                    if confirm == 'y' or confirm == 'yes':
                        conf_allowed = True
                        installation(conf_allowed, config, "", restart=True)
                    elif confirm in ['n', 'no', 'abort', 'a']:
                        pass
                elif selection == 'c' or selection == 'cgit':
                    confirm_valid_options = ['y', 'yes', 'n', 'no', 'abort', 'a']
                    while True:
                        confirm = input("\n\t\tAre you sure? [yes/abort]\t").strip()
                        if confirm in confirm_valid_options:
                            break
                        else:
                            print("\nPlease type the correct answer")
                    if confirm == 'y' or confirm == 'yes':
                        conf_allowed = True
                        git_flag = "git" if selection == 'cgit' else ''
                        installation(conf_allowed, config, git_flag, restart=True)
                    elif confirm in ['n', 'no', 'abort', 'a']:
                        pass
                elif selection == 'a':
                    clear_the_screen()
                    sleep(0.1)
                    break
            else:
                conf_allowed = True
                git_flag = "git" if selection == "igit" else ""
                installation(conf_allowed, config, git_flag)
        elif selection == 'u':
            update(config, "")
        elif selection == 'ugit':
            update(config, "git")
        elif selection == 'd':
            origin_change(config)
        elif selection == 'e':
            clear_the_screen()
            os.chdir(f"/home/{config.user}/RH_Install-Manager")
            sleep(0.1)
            break


def main():
    config = rhim_load_config()
    main_window(config)


if __name__ == "__main__":
    main()
