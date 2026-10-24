from modules import show_ip, logo_top, clear_the_screen, write_json
import json
import os
import subprocess
from time import sleep
from pathlib import Path


def conf_check():
    home_dir = str(Path.home())
    conf_now_flag = 1
    ethernet_ip, wlan_ip = show_ip()

    ap_config = {}  # Initialize ap_config as an empty dictionary

    if os.path.exists(f"{home_dir}/RH_Install-Manager/ap-config.json"):
        with open(f"{home_dir}/RH_Install-Manager/ap-config.json", "r") as json_file:
            ap_config = json.load(json_file)

        ssid = ap_config.get("WIFI", {}).get("SSID")
        password = ap_config.get("WIFI", {}).get("PASSWORD")
        ethernet_ip, wlan_ip = show_ip()

        print(f"""\n
        Looks like you have AccessPoint already configured.

              Current configuration:

        Ethernet IP: {ethernet_ip}
        Hotspot IP:  {wlan_ip}
        
        SSID (hotspot name): {ssid}
        Password (password): {password}
        \n\n""")

        while True:
            cont_conf = input("\tOverwrite and continue anyway? [Y/n]\t\t").lower()
            if not cont_conf:
                print("Answer defaulted to: yes")
                break
            elif cont_conf[0] == 'y':
                conf_now_flag = True
                break
            elif cont_conf[0] == 'n':
                conf_now_flag = False
                break
            else:
                print("\nPlease enter correct value")

    else:
        while True:
            print("""

        You are about to enable automatic Wi-Fi hotspot on your timer. 
        If no known network is found, the timer will create a self-hosting hotspot
        that can be connected to on address: 10.42.0.1 (or <your_hostname>.local)
        It checks for available networks after every reboot.
        
            """)
            print(f"""
        Current configuration:
        Ethernet IP: {ethernet_ip}
        Wi-Fi IP:    {wlan_ip}\n""")
            confirm_conf = input("""
        Do you want to continue? [Y/n]\t\t""").lower()
            if not confirm_conf:
                print("Answer defaulted to: yes")
                break
            elif confirm_conf[0] == 'y':
                conf_now_flag = True
                break
            elif confirm_conf[0] == 'n':
                conf_now_flag = False
                break
            else:
                print("\nPlease enter correct value")

    return conf_now_flag


def save_config_os(ssid, password):
    try:
        result = subprocess.run(['scripts/net_hotspot_auto_12.sh', ssid, password])
    except (OSError, ValueError):
        print("\n\tCould not run hotspot configuration. Check the setup script and input.")
        return False
    if result.returncode != 0:
        print("\n\tHotspot configuration failed (exit status {}). See the error above.".format(result.returncode))
        return False
    return True


def do_config():
    clear_the_screen()
    logo_top(False)

    home_dir = str(Path.home())
    conf_now_flag = conf_check()

    if conf_now_flag:
        clear_the_screen()
        logo_top(False)
        ap_config = {}

        print("""\n\t\t\tEnter hotspot configuration:\n""")

        ssid = input("\n\t\tEnter SSID (hotspot name):          ")
        ap_config["WIFI"] = {"SSID": ssid}

        while True:
            password = input("\n\t\tEnter Password (min. 8 characters): ")
            if len(password) < 8:
                print("\n\t\tPassword should be at least 8 characters long")
            else:
                break

        ap_config["WIFI"]["PASSWORD"] = password

        ap_configuration_summary = f"""
        
        
            WIFI SSID:          {ap_config["WIFI"]["SSID"]}
            WIFI Password:      {ap_config["WIFI"]["PASSWORD"]}

            Please check. Confirm? [yes/change/abort]
"""
        print(ap_configuration_summary)

        valid_options = ['y', 'yes', 'n', 'no', 'ch', 'change', 'abort']
        while True:
            selection = input().strip()
            if selection in valid_options:
                break
            else:
                print("\nPlease enter correct value")
        if selection[0] == 'y':
            if not save_config_os(ssid, password):
                input("\n\tHit 'Enter' to exit this screen ")
                return 0
            try:
                write_json(ap_config, f"{home_dir}/RH_Install-Manager/ap-config.json")
            except OSError:
                print("\n\tHotspot service configured, but ap-config.json could not be saved. Check file permissions and free space.")
                input("\n\tHit 'Enter' to exit this screen ")
                return 0
            print("\n\n\tHotspot configuration data has been saved\n")
            sleep(3)
            clear_the_screen()
            logo_top(False)
            ethernet_ip, wlan_ip = show_ip()
            print(f"""\n\n
            Current configuration: 

            Ethernet IP: {ethernet_ip}
            Hotspot IP:  {wlan_ip}
            
            SSID (hotspot name): {ssid}
            Password (password): {password}\n\n""")

            input("\n\tHit 'Enter' to exit this screen ")
            conf_now_flag = 0
        if selection in ['ch', 'change', 'n', 'no']:
            conf_now_flag = 1
        if selection == 'abort':
            print("Configuration aborted.\n")
            sleep(0.5)
            conf_now_flag = 0

    return conf_now_flag


def net_hotspot_auto_12():
    config_now = 1
    while config_now:
        config_now = do_config()


def main():
    net_hotspot_auto_12()


if __name__ == "__main__":
    main()
