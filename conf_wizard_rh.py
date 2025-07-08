import os
from pathlib import Path
from time import sleep
from modules import clear_the_screen, Bcolors, logo_top, write_json


def conf_check():
    conf_now_flag = 1
    if os.path.exists(f"./../RotorHazard/src/server/config.json"):
        print("\n\tYou have already configured Rotorhazard.")
        while True:
            cont_conf = input("\n\tOverwrite and continue anyway? [Y/n]\t\t").lower()
            if not cont_conf:
                print("\nanswer defaulted to: yes")
                break
            elif cont_conf[0] == 'y':
                conf_now_flag = True
                break
            elif cont_conf[0] == 'n':
                conf_now_flag = False
                break
            else:
                print("\nPlease enter a valid selection")

    return conf_now_flag


def do_config():
    home_dir = str(Path.home())
    clear_the_screen()
    logo_top(False)

    conf_now_flag = conf_check()

    if conf_now_flag:
        rh_config = {}
        print("""\n
Please type your configuration data. It can be modified later.
If you want to use value given as default, just hit 'Enter'.
""")
        nuclear_flag = False
        print("\nAre you using NuclearHazard timer? [y/N]"
              "\nIf you are, some settings can be automatically applied\t")
        while True:
            nuclear_user = input("\t").strip().lower()
            if not nuclear_user:
                print("defaulted to: 'no'")
                nuclear_flag = False
                break
            elif nuclear_user[0] == 'y':
                nuclear_flag = True
                break
            elif nuclear_user[0] == 'n':
                nuclear_flag = False
                break
            else:
                print("\nPlease enter a valid selection")

        rh_config['GENERAL'] = {}

        if nuclear_flag:
            admin_name = "NuclearHazard"
        else:
            admin_name = input("\nWhat will be admin user name on RotorHazard page? [default: admin]\t")
            if not admin_name:
                admin_name = 'admin'
                print("defaulted to: 'admin'")
        rh_config['GENERAL']["ADMIN_USERNAME"] = admin_name

        if nuclear_flag:
            admin_pswd = "nuclearhazard"
        else:
            admin_pswd = input("\nWhat will be admin password on RotorHazard page? [default: rotorhazard]\t")
            if not admin_pswd:
                admin_pswd = 'rotorhazard'
                print("defaulted to: 'rotorhazard'")

        rh_config['GENERAL']["ADMIN_PASSWORD"] = admin_pswd

        while True:
            http_port_nr = input("\nWhich port will you use with RotorHazard? [default (and advised): 5000]\t")
            if not http_port_nr:
                http_port_nr = 5000
                print("defaulted to: 5000")
                break
            elif http_port_nr.isdigit():
                break
            elif not http_port_nr.isdigit():
                print("\nPlease enter a valid selection")
        rh_config['GENERAL']['HTTP_PORT'] = int(http_port_nr)

        rh_config['SENSORS'] = {}
        rh_config['LED'] = {}
        rh_config['HARDWARE'] = {}

        while True:
            print("\nAre you planning to use LEDs in your system? [y/N]\n")
            selection = input("\t").lower()
            if not selection:
                led_present_flag = False
                print("defaulted to: no")
                break
            if selection[0] == 'y':
                led_present_flag = True
                break
            elif selection[0] == 'n':
                led_present_flag = False
                break
            else:
                print("\nPlease enter a valid selection")

        if led_present_flag:
            while True:
                led_amount = input("\nHow many LEDs will you use in your system?\t\t\t\t")
                if led_amount.isdigit():
                    break
                else:
                    print("\nPlease enter a valid selection")
            rh_config['LED']['LED_COUNT'] = int(led_amount)

            while True:
                led_rows_amount = input("\nHow many LED rows will you use in your system?\t\t\t\t")
                if led_rows_amount.isdigit():
                    break
                else:
                    print("\nPlease enter a valid selection")
            rh_config['LED']['LED_ROWS'] = int(led_rows_amount)

            while True:
                led_data_pin_nr = input("\nWhich GPIO pin is connected to your LEDs data pin? [default: 10]\t")
                led_pins_allowed = ['10', '12', '13', '18', '19', '21', '31', '38', '40', '41', '45', '52', '53']
                if not led_data_pin_nr:
                    led_data_pin_nr = 10
                    print("defaulted to: 10")
                    break
                elif led_data_pin_nr in led_pins_allowed:
                    led_data_pin_nr = int(led_data_pin_nr)
                    break
                elif led_data_pin_nr.isdigit() and led_data_pin_nr not in led_pins_allowed:
                    print("That pin cannot be used for that purpose")
                else:
                    print("\nPlease enter a valid selection")
            rh_config['LED']['LED_GPIO'] = int(led_data_pin_nr)

            while True:
                led_output_inverted = input("\nIs LED data pin output inverted? [y/N]\t\t\t\t\t").lower()
                if not led_output_inverted:
                    led_output_inverted = False
                    print("defaulted to: no")
                    break
                elif led_output_inverted[0] == 'y':
                    led_output_inverted = True
                    break
                elif led_output_inverted[0] == 'n':
                    led_output_inverted = False
                    break
                else:
                    print("\nPlease enter a valid selection")
            rh_config['LED']['LED_INVERT'] = led_output_inverted

            while True:
                led_channel_nr = input("\nWhat channel (not pin!) will be used with your LEDs? [default: 0]\t")
                if not led_channel_nr:
                    led_channel_nr = 0
                    print("defaulted to: 0")
                    break
                elif led_channel_nr.isdigit():
                    break
                else:
                    print("\nPlease enter a valid selection")
            rh_config['LED']['LED_CHANNEL'] = int(led_channel_nr)

            while True:
                led_strip = input("\nWhat strip type and color ordering are you using? [default: 'GRB']\t")
                if not led_strip:
                    led_strip = 'GRB'
                    print("defaulted to: 'GRB'")
                    break
                elif led_strip.isdigit():
                    print("\nPlease enter correct type!")
            rh_config['LED']['LED_STRIP'] = str(led_strip)

            while True:
                led_panel_rotation = input("\nBy how many degrees is your panel rotated? [0/90/180/270 | default: 0]\t")
                panel_rot_values_allowed = ['0', '90', '180', '270']
                if not led_panel_rotation:
                    led_panel_rotation = 0
                    print("defaulted to: 0")
                    break
                elif led_panel_rotation in panel_rot_values_allowed:
                    led_panel_rotation = (int(led_panel_rotation) / 90)
                    break
                else:
                    print("\nPlease enter a valid selection")
            rh_config['LED']['PANEL_ROTATE'] = int(led_panel_rotation)

            while True:
                led_rows_inverted = input("\nAre your panel rows inverted? [y/N]\t\t\t\t\t").lower()
                if not led_rows_inverted:
                    led_rows_inverted = False
                    print("defaulted to: no")
                    break
                elif led_rows_inverted[0] == 'y':
                    led_rows_inverted = True
                    break
                elif led_rows_inverted[0] == 'n':
                    led_rows_inverted = False
                    break
                else:
                    print("\nPlease enter a valid selection")
            rh_config['LED']['INVERTED_PANEL_ROWS'] = led_rows_inverted

            while True:
                led_dma_nr = input("\nLED DMA you will use in your system? [default: 10]\t\t\t")
                if not led_dma_nr:
                    led_dma_nr = 10
                    print("defaulted to: 10")
                    break
                elif led_dma_nr.isdigit():
                    break
                else:
                    print("\nPlease enter a valid selection")
            rh_config['LED']['LED_DMA'] = int(led_dma_nr)

            while True:
                led_frequency = input("\nWhat LED frequency will you use? [default: 800000]\t\t\t")
                if not led_frequency:
                    led_frequency = 800000
                    print("defaulted to: 800000")
                    break
                elif led_frequency.isdigit() and int(led_frequency) < 800000:
                    break
                else:
                    print("\nPlease enter a valid selection")
            rh_config['LED']['LED_FREQ_HZ'] = int(led_frequency)

        if not led_present_flag:
            rh_config['LED']['LED_COUNT'] = 0
            rh_config['LED']['LED_ROWS'] = 0
            rh_config['LED']['LED_GPIO'] = 10
            rh_config['LED']['LED_INVERT'] = False
            rh_config['LED']['LED_CHANNEL'] = 0
            rh_config['LED']['LED_STRIP'] = 'GRB'
            rh_config['LED']['PANEL_ROTATE'] = 0
            rh_config['LED']['INVERTED_PANEL_ROWS'] = False
            rh_config['LED']['LED_DMA'] = 10
            rh_config['LED']['LED_FREQ_HZ'] = 800000
            print("\nLED configuration set to default values.\n\n")
            sleep(1.2)

        print("\nDo you want to enter advanced configuration? [y/N]\n")
        while True:
            advanced_wizard_flag = input("\t").strip().lower()
            if not advanced_wizard_flag:
                print("defaulted to: no")
                advanced_wizard_flag = False
                break
            elif advanced_wizard_flag[0] == 'y':
                advanced_wizard_flag = True
                break
            elif advanced_wizard_flag[0] == 'n':
                advanced_wizard_flag = False
                break
            else:
                print("\nPlease enter a valid selection")

        if advanced_wizard_flag:

            while True:
                i2c_bus_nr = input("\nWhat is the I2C bus number on your device? [default: 1]\t\t\t")
                if not i2c_bus_nr:
                    i2c_bus_nr = 1
                    print("defaulted to: 1")
                    break
                elif i2c_bus_nr.isdigit() and int(i2c_bus_nr) < 3:
                    break
                else:
                    print("\nPlease enter a valid selection")
            rh_config['HARDWARE']['I2C_BUS'] = int(i2c_bus_nr)

            while True:
                debug_mode = input("\nWill you use RotorHazard in debug mode? [y/N]\t\t\t\t").lower()
                if not debug_mode:
                    debug_mode = False
                    print("defaulted to: no")
                    break
                elif debug_mode[0] == 'y':
                    debug_mode = True
                    break
                elif debug_mode[0] == 'n':
                    debug_mode = False
                    break
                else:
                    print("\nPlease enter a valid selection")
            rh_config['GENERAL']['DEBUG'] = debug_mode

            cors = input("\nCORS hosts allowed? [default: all]\t\t\t\t\t")
            if not cors:
                cors = "*"
                print("defaulted to: all")
            elif cors in ['*', 'all']:
                cors = "*"
            rh_config['GENERAL']['CORS_ALLOWED_HOSTS'] = cors

            while True:
                serial_ports = input(
                    "\nWhich port (serial or USB) you will use? [blank defaults to serial0]\t").strip()
                if not serial_ports:
                    serial_ports = []
                    print("defaulted to: []")
                    break
                else:
                    serial_ports = [f"/dev/{serial_ports}"]
                    break
            rh_config['SERIAL_PORTS'] = serial_ports

            if nuclear_flag:
                shutdown_pin = 19
            else:
                while True:
                    shutdown_pin = input(
                        "\nWhich pin is connected to the shutdown button? [default: 18]\t\t").strip().lower()
                    if not shutdown_pin:
                        shutdown_pin = 18
                        print("defaulted to: 18")
                        break
                    elif shutdown_pin.isdigit():
                        break
                    else:
                        print("\nPlease enter a valid selection")
            rh_config['GENERAL']['SHUTDOWN_BUTTON_GPIOPIN'] = shutdown_pin

            if nuclear_flag:
                shutdown_debounce = 2500
            else:
                while True:
                    shutdown_debounce = input(
                        "\nShutdown button delay in microseconds [default: 5000]\t\t\t").strip().lower()
                    if not shutdown_debounce:
                        shutdown_debounce = 5000
                        print("defaulted to: 5000")
                        break
                    elif shutdown_debounce.isdigit() and int(shutdown_debounce) > 500:
                        break
                    else:
                        print("\nPlease enter a valid selection")
            rh_config['GENERAL']['SHUTDOWN_BUTTON_DELAYMS'] = shutdown_debounce

        if not advanced_wizard_flag:
            rh_config['HARDWARE']['I2C_BUS'] = 1
            rh_config['GENERAL']['DEBUG'] = False
            rh_config['GENERAL']['CORS_ALLOWED_HOSTS'] = '*'
            rh_config['SERIAL_PORTS'] = []
            if nuclear_flag:
                rh_config['GENERAL']['SHUTDOWN_BUTTON_GPIOPIN'] = 19
                rh_config['GENERAL']['SHUTDOWN_BUTTON_DELAYMS'] = 2500
            else:
                rh_config['GENERAL']['SHUTDOWN_BUTTON_GPIOPIN'] = 18
                rh_config['GENERAL']['SHUTDOWN_BUTTON_DELAYMS'] = 5000
            print("\nAdvanced configuration set to default values.\n\n")
            sleep(1.2)

        rh_configuration_summary = f"""\n\n
            {Bcolors.UNDERLINE}CONFIGURATION{Bcolors.ENDC}
        
        NuclearHazard:      {nuclear_flag}
        Admin name:         {rh_config['GENERAL']['ADMIN_USERNAME']}
        Admin password:     {rh_config['GENERAL']['ADMIN_PASSWORD']}
        RotorHazard port:   {rh_config['GENERAL']['HTTP_PORT']}
        LED amount:         {rh_config['LED']['LED_COUNT']}
        LED rows:           {rh_config['LED']['LED_ROWS']}
        LED gpio:           {rh_config['LED']['LED_GPIO']}
        LED inverted:       {rh_config['LED']['LED_INVERT']}
        LED channel:        {rh_config['LED']['LED_CHANNEL']}
        LED strip:          {rh_config['LED']['LED_STRIP']}
        LED panel rotated:  {rh_config['LED']['PANEL_ROTATE']}
        LED rows inverted:  {rh_config['LED']['INVERTED_PANEL_ROWS']}
        LED DMA:            {rh_config['LED']['LED_DMA']}
        LED frequency:      {rh_config['LED']['LED_FREQ_HZ']}
        I2C bus number:     {rh_config['HARDWARE']['I2C_BUS']}
        Debug mode:         {rh_config['GENERAL']['DEBUG']}
        CORS allowed:       {rh_config['GENERAL']['CORS_ALLOWED_HOSTS']}
        Serial ports:       {rh_config['SERIAL_PORTS']}
        Shutdown pin:       {rh_config['GENERAL']['SHUTDOWN_BUTTON_GPIOPIN']}
        Shutdown debounce:  {rh_config['GENERAL']['SHUTDOWN_BUTTON_DELAYMS']}


        Please check. Confirm? [yes/change/abort]\n"""
        print(rh_configuration_summary)
        valid_options = ['y', 'yes', 'n', 'no', 'change', 'ch', 'abort']
        while True:
            selection = input().strip()
            if selection in valid_options:
                break
            else:
                print("\nPlease enter a valid selection")
        if selection[0] == 'y':
            write_json(rh_config, f"{home_dir}/RotorHazard/src/server/config.json")
            print(f"\n{Bcolors.UNDERLINE}Configuration saved{Bcolors.ENDC}\n")
            os.system(
                f"{home_dir}/RH_Install-Manager/scripts/additional_sys_conf.sh shutdown_pin {rh_config['GENERAL']['SHUTDOWN_BUTTON_GPIOPIN']} "
                f"{rh_config['GENERAL']['SHUTDOWN_BUTTON_DELAYMS']}")
            os.system(f"{home_dir}/RH_Install-Manager/scripts/additional_sys_conf.sh led ")
            print(f"\nreboot maybe required\n")
            sleep(5)
            conf_now_flag = 0
        if selection in ['ch', 'change', 'n', 'no']:
            conf_now_flag = 1
        if selection == 'abort':
            print(f"\n{Bcolors.UNDERLINE}Configuration aborted{Bcolors.ENDC}\n")
            sleep(1.5)
            conf_now_flag = 0

    return conf_now_flag


def conf_rh():
    """
        repeat the configuration script until
        the user either aborts, configures rhim
        or it was already configured.
    :return:
    """
    config_now = 1
    while config_now:
        config_now = do_config()


def main():
    conf_rh()


if __name__ == "__main__":
    main()
