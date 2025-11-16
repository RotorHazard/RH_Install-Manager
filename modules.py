import json
import os
import platform
import socket
import subprocess
import sys
import time
import pwd
from pathlib import Path
from shutil import copyfile
from time import sleep
from types import SimpleNamespace as Namespace, SimpleNamespace
import requests


def host_sys_info():
    host_info = os.system("./scripts/get_host_info.sh")
    host = True if host_info == 256 else False  # value 256 means 1 was returned by a script
    return host


def show_ip():
    ethernet_ip_os = r"ifconfig eth0 | grep -oP 'inet \K\S+' || sudo ifconfig eth0 | grep -oP 'inet \K\S+' || echo 'no wired connection'"
    ethernet_ip = (subprocess.check_output(ethernet_ip_os, shell=True, text=True)).strip()
    hotspot_ip_os = r"ifconfig wlan0 | grep -oP 'inet \K\S+' || sudo ifconfig wlan0 | grep -oP 'inet \K\S+' || echo 'no wireless connection'"
    wlan_ip = (subprocess.check_output(hotspot_ip_os, shell=True, text=True)).strip()
    return ethernet_ip, wlan_ip


def get_host_info():
    ip_list = []
    try:
        hostname = socket.gethostname()
        ip_addresses = subprocess.check_output(['hostname', '-I']).decode('utf-8').strip().split()
        for ip in ip_addresses:
            ip_list.append(ip) if len(ip) < 16 else None
        for i in range(3):
            ip_list.append("0")  # so at least ip_list have at least 3 arguments - due to return function

    except Exception as e:
        hostname = "no hostname info"

    return hostname, ip_list


def name_check():
    username = pwd.getpwuid(os.getuid()).pw_name
    return username


def clear_the_screen():
    sleep(0.02)
    if platform.system() == "Windows":
        os.system("cls")
    elif platform.system() == "Linux" or platform.system() == "Darwin":
        os.system("clear")
    else:
        print(("\n" * 200))
    sleep(0.02)


def dots_show(duration):
    for i in range(30):
        sys.stdout.write(".")
        sys.stdout.flush()
        sleep(duration / 30)
    sys.stdout.write("\n")


def percent_count():
    def backspace(n):
        sys.stdout.write((b'\x08' * n).decode())  # use \x08 char to go back

    for i in range(101):  # for 0 to 100
        s = str(i) + '%'  # string for output
        sys.stdout.write(s)  # just print
        sys.stdout.flush()  # needed for flush when using \x08
        backspace(len(s))  # back n chars
        time.sleep(0.05)


def triangle_image_show():
    with open('./resources/image.txt', 'r') as logo:
        f = logo.read()
        print(f"{Bcolors.YELLOW}{f}{Bcolors.ENDC}")


def rhim_asci_image_show():
    with open('resources/rhim_image.txt', 'r') as file:
        f = file.read()
        print(f)


def check_if_string_is_in_file(file_name, string_to_search):
    with open(file_name, 'r') as read_obj:
        for line in read_obj:
            if string_to_search in line:
                return True
    return False


def logo_top(linux_testing):
    hostname = str(get_host_info()[0])
    ip1 = str("IP: " + get_host_info()[1][0]) if get_host_info()[1][0] != "0" else "IP: no IP info"
    ip2 = str("IP: " + get_host_info()[1][1]) if get_host_info()[1][1] != "0" else ""
    ip3 = str("IP: " + get_host_info()[1][2]) if get_host_info()[1][2] != "0" else ""
    debug_status = f"{Bcolors.PROMPT}Debug 'PC' version - sim mode{Bcolors.ENDC}" if linux_testing else 29 * ' '
    print("""

  #####################################   
  ##                                 ##   Hostname: {hostname}  
  ##{orbold}   RotorHazard     {endc}##      
  ##                                 ##   {ip1}             
  ##{bold}   Install-Manager {endc}  ##   {ip2}             
  ##  {place_for_debug_status_here}  ##   {ip3}             
  #####################################    
    """.format(bold=Bcolors.BOLD_S, endc=Bcolors.ENDC_S, place_for_debug_status_here=debug_status,
               yellow=Bcolors.YELLOW_S, orbold=(Bcolors.BOLD + Bcolors.ORANGE + 8 * " "), hostname=hostname,
               ip1=ip1, ip2=ip2, ip3=ip3))


class Bcolors:
    HEADER = '\033[95m'
    ORANGE = '\033[33m'
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    BLINK = '\033[5m'
    GREEN_BACK = '\033[102m'
    ORANGE_BACK = '\033[103m'
    RED_MENU_HEADER = '\033[91m' + '\033[1m' + '\033[4m'
    PROMPT = '\033[30m' + '\033[103m' + '\033[1m'
    '''
    the following are designed to be used in formatted strings
    they each have enough spaces appended so that {value}
    will be replaced with an equal number of spaces.
    '''
    HEADER_S = '\033[95m' + (' ' * 9)
    ORANGE_S = '\033[33m' + (' ' * 8)
    BLUE_S = '\033[94m' + (' ' * 6)
    GREEN_S = '\033[92m' + (' ' * 7)
    YELLOW_S = '\033[93m' + (' ' * 8)
    RED_S = '\033[91m' + (' ' * 5)
    ENDC_S = '\033[0m' + (' ' * 6)
    BOLD_S = '\033[1m' + (' ' * 6)
    UNDERLINE_S = '\033[4m' + (' ' * 11)


def internet_check():
    print("""

        Please wait - checking internet connection state....

    """)
    internet_flag = False
    for i in range(3):
        try:
            response = requests.get('https://github.com')
        except Exception:
            response = False

        if response and response.status_code == requests.codes.ok:
            internet_flag = True
            break
    return internet_flag


def load_rhim_sys_markers(user):
    rhim_config_file = f'/home/{user}/.rhim_markers/rhim_config.json'
    if Path(rhim_config_file).exists():
        rhim_config = load_json(rhim_config_file)
    else:
        rhim_config = load_json(f'/home/{user}/RH_Install-Manager/resources/rhim_config.json')
    return rhim_config


def write_rhim_sys_markers(rhim_config, user):
    rhim_config_file = f'/home/{user}/.rhim_markers/rhim_config.json'
    write_json(rhim_config, rhim_config_file)


def get_rhim_version(checking_from_updater):
    config = rhim_load_config()
    if checking_from_updater:
        path = f'/home/{config.user}/RH_Install-Manager/'
    else:
        path = os.path.dirname(os.path.realpath(__file__))
    try:
        with open(f'{path}/version.txt', 'r') as open_file:
            version = open_file.readline().strip()
    except:
        version = "can't read Install-Manager version"
    return version


def server_start():
    server_stat = os.popen('service rotorhazard status').read()
    if 'running' not in server_stat:
        clear_the_screen()
        os.system("./scripts/server_start.sh")
    else:
        clear_the_screen()
        print("Server is already running as a service")
        selection = input("Do you want to stop it and than start the server again? [y/n] ")
        if selection == 'y':
            os.system("sudo systemctl stop rotorhazard")
            print("Server service stopped. Please wait.\n")
            os.system("./scripts/server_start.sh")


def rhim_config_check():
    if not os.path.exists("./updater-config.json"):
        prompt = """
          {prompt}  Looks that you haven't set up config file yet.  {endc}
          {prompt}  Please enter Configuration Wizard - point 4     {endc}""" \
            .format(prompt=Bcolors.PROMPT + Bcolors.BLUE, endc=Bcolors.ENDC)
        print(prompt)
        return False
    else:
        return True


def rhim_load_config():
    if os.path.exists("./updater-config.json"):
        config = load_json("./updater-config.json")
    else:
        config = load_json('./distr-updater-config.json')

    if config.debug_mode:
        config.user = config.debug_user
    else:
        config.user = config.user
    # paste custom version number here if you want to declare it manually
    return config


'''
This is a convenience method that uses lambda functions
to convert json data into accessible objects. 
Given file with:
{
    "name": "John Smith", 
    "hometown": {
        "name": "New York"
        , "id": 123
    }
}

running:
data = load_json(file_name) 

will let you do:
print(data.hometown.name)
>>> New York
'''


def load_json(file_name):
    data = {}
    if os.path.exists(file_name):
        with open(file_name) as open_file:
            data = json.loads(open_file.read(), object_hook=lambda d: Namespace(**d))
    return data


'''
quick wrapper around write json to normalize our parameters.
'''


def write_json(to_dump, file_name):
    with open(file_name, 'w') as open_file:
        if isinstance(to_dump, SimpleNamespace):
            json.dump(vars(to_dump), open_file, indent=4)
        else:
            json.dump(to_dump, open_file, indent=4)


'''
 wrapper around copy file to check if exists before copying
'''


def copy_file(src, tgt):
    if os.path.exists(src):
        copyfile(src, tgt)
