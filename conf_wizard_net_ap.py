from time import sleep
from modules import clear_the_screen, Bcolors, logo_top, write_json
from pathlib import Path
import json
import os


def check_existing_config():
    if os.path.exists("ap-config.json"):
        with open("ap-config.json", "r") as json_file:
            current_config = json.load(json_file)
            print("\n\t\t\tYou already configured the hotspot\n")
            print("\t\t\tCurrent Configuration:")
            for key, value in current_config.items():
                print(f"\t\t\t{key}: {value}")

        change_config = input("\n\t\t\tDo you want to change the existing configuration? (y/n): ").lower()
        if change_config != 'y':
            print("\t\t\tExiting without making changes\n")
            sleep(2)
            exit()
        clear_the_screen()
        logo_top(False)


def get_user_input():
    print("\n\n")
    ssid = input("\t\t\tEnter SSID (hotspot name):               ")
    password = input("\t\t\tEnter Password (min. 8 characters):      ")
    return ssid, password


def display_and_confirm_config(ssid, password):
    print("\n\t\t\tProvided Configuration:")
    print(f"\t\t\tSSID (hotspot name): {ssid}")
    print(f"\t\t\tPassword: {password}")
    print("\n\n")

    confirm_save = input("\t\t\tDo you want to save this configuration? (y/n): ").lower()
    print("\n")
    if confirm_save != 'y':
        print("Exiting without saving the configuration")
        exit()


def save_config_to_json(ssid, password):
    config_data = {
        "SSID": ssid,
        "Password": password
    }

    with open("ap-config.json", "w") as json_file:
        json.dump(config_data, json_file, indent=4)


def save_config_os(ssid, password):
    os.system("sudo nmcli con delete hotspot")
    os.system(f"sudo nmcli con add con-name hotspot ifname wlan0 type wifi ssid {ssid}")
    os.system(f"sudo nmcli con modify hotspot wifi-sec.key-mgmt wpa-psk")
    os.system(f"sudo nmcli con modify hotspot wifi-sec.psk '{password}'")
    os.system(f"sudo nmcli con modify hotspot 802-11-wireless.mode ap 802-11-wireless.band bg ipv4.method shared")
    print("\n\n\t\t\tHotspot configuration data has been saved\n")
    sleep(3)


def ap_config():
    clear_the_screen()
    logo_top(False)
    check_existing_config()
    ssid, password = get_user_input()
    display_and_confirm_config(ssid, password)
    save_config_to_json(ssid, password)
    save_config_os(ssid, password)


def main():
    ap_config()


if __name__ == "__main__":
    main()
