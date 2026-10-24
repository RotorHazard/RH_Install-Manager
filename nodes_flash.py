import os
from time import sleep
from modules import clear_the_screen, Bcolors, logo_top, rhim_load_config
from nodes_flash_common import prepare_mate_node, reset_gpio_pin


def nodes_addresses():
    # nodes I2C addresses - below: hex format is required by SMBus module
    # "RH" are address in RotorHazard node firmware code "format" (rhnode file)

    #  node     addr   RH
    node1addr = 0x08  # 8   - 1st node I2C hardware address
    node2addr = 0x0a  # 10  - 2nd node I2C hardware address
    node3addr = 0x0c  # 12  - 3rd node I2C hardware address
    node4addr = 0x0e  # 14  - 4th node I2C hardware address
    node5addr = 0x10  # 16  - 5th node I2C hardware address
    node6addr = 0x12  # 18  - 6th node I2C hardware address
    node7addr = 0x14  # 20  - 7th node I2C hardware address
    node8addr = 0x16  # 22  - 8th node I2C hardware address

    # addresses are swapped in the list due to "paired" nature of resetting before flashing
    # sending a command to first element on the list causes second node to be flashed etc.

    addr_list = [node2addr, node1addr, node4addr, node3addr,
                 node6addr, node5addr, node8addr, node7addr]

    return addr_list


def firmware_version_selection(config):
    if config.rh_version in ['stable', 'beta']:
        firmware_version = config.rh_version
    elif config.rh_version in ['master', 'main']:
        firmware_version = 'main'
    else:  # in case of 'custom' RH version - firmware defaults to 'stable'
        firmware_version = 'stable'

    return firmware_version


def successful_update_image(config):
    print("""
    #######################################################################
    #                                                                     #
    # {bg}{s}Flashing firmware onto {nodes_number} nodes - DONE{endc}{s} #
    #                                                                     #
    #              {bold}         Thank you!        {endc}                #
    #                                                                     #
    #######################################################################\n\n
    """.format(nodes_number=config.nodes_number, bold=Bcolors.BOLD_S,
               bg=Bcolors.BOLD_S + Bcolors.GREEN, endc=Bcolors.ENDC_S, s=(9 * ' ')))


def unsuccessful_update_image():
    print("""{yellow}
    #######################################################################
    #                                                                     #
    #            There were some nodes that couldn't be flashed.          #
    #                                                                     #
    #                    Please scroll up and check.                      #
    #                                                                     # 
    #######################################################################\n\n
    {endc}""".format(bold=Bcolors.BOLD_S, bg=Bcolors.BOLD_S + Bcolors.GREEN,
                     yellow=Bcolors.YELLOW, endc=Bcolors.ENDC_S, s=(9 * ' ')))


def odd_number_of_nodes_check(config):
    nodes_number = config.nodes_number
    odd_nodes_flag = True if nodes_number % 2 != 0 else False
    return odd_nodes_flag


def firmware_flash(config, bootloader_version=0, flashing_target="firmware", attempt=0):
    if bootloader_version == 0:
        flashing_baudrate = 57600
        bootloader_version = "old_bootloader"
    else:
        flashing_baudrate = 115200
        bootloader_version = "new_bootloader"

    if flashing_target == "firmware":
        firmware_version = f"{firmware_version_selection(config)}/node_0.hex"
    elif flashing_target == "blink":
        firmware_version = "blink.hex"
    else:
        firmware_version = "custom_firmware/custom_node.hex"

    command = (
        f"timeout 13 avrdude -v -p atmega328p -c arduino -P /dev/{config.port_name} -b {flashing_baudrate} -U "
        f"flash:w:/home/{config.user}/RH_Install-Manager/firmware/{bootloader_version}/{firmware_version}:i")
    print(command)
    return not config.debug_mode and os.system(command) == 0


def node_operation(config, selected_node_number, gpio_node=False, firmware_type="firmware",
                   uart=False, initial_bootloader=0):
    if config.debug_mode:
        print("simulation mode - UART unavailable" if uart else "simulation mode - flashing disabled")
        return False
    addr = nodes_addresses()[selected_node_number - 1]
    for attempt in range(2):
        try:
            if gpio_node:
                print(f"Node {selected_node_number} - reset with GPIO pin: {config.gpio_reset_pin}")
                reset_gpio_pin(config.gpio_reset_pin)
            else:
                print(f"Node {selected_node_number} - reset with I2C address: {addr}")
                prepare_mate_node(addr)
        except Exception as error:
            print(f"Node {selected_node_number} - reset failed: {error}")
            return False
        bootloader = initial_bootloader if attempt == 0 else 1 - initial_bootloader
        if uart:
            success = check_uart_connection(config, bootloader, attempt)
        else:
            success = firmware_flash(config, bootloader, firmware_type, attempt)
        if success:
            return True
        if attempt == 0:
            print("Unsuccessful attempt - trying with another bootloader")
    return False


# below works when nodes are 'auto-numbered' - as when official PCB is used
def all_nodes_flash(config):
    clear_the_screen()
    print(f"\n\t\t\t{Bcolors.BOLD}Flashing procedure started{Bcolors.BOLD}\n\n")
    success = True
    for node in range(1, config.nodes_number + 1):
        gpio_node = odd_number_of_nodes_check(config) and node == config.nodes_number
        result = node_operation(config, node, gpio_node)
        print(f"Node {node} - {'flashed' if result else 'not flashed'}")
        success = result and success
        sleep(2)
    unsuccessful_update_image() if not success else successful_update_image(config)
    input("\nDone. Press ENTER to continue ")
    sleep(1)
    return success


def flash_firmware_onto_a_node(config, selected_node_number, gpio_node=False, firmware_type="firmware"):
    success = node_operation(config, selected_node_number, gpio_node, firmware_type)
    print(f"Node {selected_node_number} - {'flashed' if success else 'not flashed'}")
    input("\nPress ENTER to continue")
    sleep(2)
    return success


def check_uart_connection(config, bootloader_version=0, attempt=0):
    flashing_baudrate = 57600 if bootloader_version == 0 else 115200
    command = f"timeout 13 avrdude -v -p atmega328p -c arduino -P /dev/{config.port_name} -b {flashing_baudrate}"
    print(command)
    return not config.debug_mode and os.system(command) == 0


def check_uart_con_with_a_node(config, selected_node_number, gpio_node=False):
    success = node_operation(config, selected_node_number, gpio_node, uart=True)
    print(f"Node {selected_node_number} - {'UART connected' if success else 'UART connection failed'}")
    sleep(1)
    input("\nPress ENTER to continue")
    return success



def node_selection_menu(config):
    while True:
        clear_the_screen()
        logo_top(config.debug_mode)
        flash_node_menu = """\n

                    {red}{bold}NODES MENU{endc}{bold}

                1 - Flash node 1        5 - Flash node 5

                2 - Flash node 2        6 - Flash node 6

                3 - Flash node 3        7 - Flash node 7

                4 - Flash node 4        8 - Flash node 8 

                   {yellow}e - Exit to main menu{endc}

        """.format(bold=Bcolors.BOLD_S, red=Bcolors.RED_S, yellow=Bcolors.YELLOW_S, endc=Bcolors.ENDC)
        print(flash_node_menu)
        selection = input(f"\t\t{Bcolors.BOLD}Which node do you want to program: {Bcolors.ENDC}")
        if selection.isdigit():
            if int(selection) not in range(config.nodes_number + 1):
                selection_confirm = input("\n\n\tNode number higher than configured amount of nodes."
                                          "\n\tAre you sure you want to continue? [y/N]\t")
                if selection_confirm.lower() == 'y':
                    selected_node_number = selection
                    specific_node_menu(config, int(selected_node_number))
            else:
                selected_node_number = selection
                specific_node_menu(config, int(selected_node_number))
        elif selection == 'e':
            break


def specific_node_menu(config, selected_node_number):
    while True:
        clear_the_screen()
        logo_top(config.debug_mode)
        node_selected_menu = f"""
        {Bcolors.BOLD}\n\t\t\tNode {str(selected_node_number)}  selected{Bcolors.ENDC}\n
                Choose flashing type:\n{Bcolors.ENDC}
        1 - {Bcolors.GREEN}Node ground-auto selection firmware - recommended{Bcolors.ENDC}{Bcolors.BOLD}

        2 - Flash custom firmware onto the node - advanced

        3 - Flash 'blink' onto the node - only for test purposes

        4 - Check UART connection with the node

        e - Exit{Bcolors.ENDC}"""
        print(node_selected_menu)
        if odd_number_of_nodes_check(config) and selected_node_number == config.nodes_number:
            gpio_node = True
        else:
            gpio_node = False
        selection = input()
        if selection == '1':
            flash_firmware_onto_a_node(config, selected_node_number, gpio_node, "firmware")
        elif selection == '2':
            flash_firmware_onto_a_node(config, selected_node_number, gpio_node, "custom")
        elif selection == '3':
            flash_firmware_onto_a_node(config, selected_node_number, gpio_node, "blink")
        elif selection == '4':
            check_uart_con_with_a_node(config, selected_node_number, gpio_node)
        elif selection == 'e':
            break
        else:
            continue
        break


def first_flashing(config):
    clear_the_screen()
    logo_top(config.debug_mode)

    success = False

    def flash_node_first_time(port):
        attempted = False
        all_successful = True
        first_attempt = f"timeout 20 avrdude -v -p atmega328p -c arduino -P /dev/{port} -b 57600 -U \
        flash:w:/home/{config.user}/RH_Install-Manager/firmware/old_bootloader/{firmware_version_selection(config)}/node_0.hex:i"
        second_attempt = f"sleep 2 && timeout 20 avrdude -v -p atmega328p -c arduino -P /dev/{port} -b 115200 -U \
        flash:w:/home/{config.user}/RH_Install-Manager/firmware/new_bootloader/{firmware_version_selection(config)}/node_0.hex:i"
        uart_flashing_prompt = \
            "\n\n\t{bg}Hit 'Enter' and push reset button on next node after a second {e}{br}[e - exit] {e}" \
            "".format(br=Bcolors.RED + Bcolors.BOLD, bg=Bcolors.GREEN + Bcolors.BOLD, e=Bcolors.ENDC)
        usb_flashing_prompt = \
            "\n\n\t{bg}Connect next Arduino and hit 'Enter'{e} {br}[e - exit] {e}" \
            "".format(br=Bcolors.RED + Bcolors.BOLD, bg=Bcolors.GREEN + Bcolors.BOLD, e=Bcolors.ENDC)
        flashing_prompt = 0
        if port == 'ttyUSB0':
            flashing_prompt = usb_flashing_prompt
        else:
            flashing_prompt = uart_flashing_prompt
        while True:
            selection = input(flashing_prompt)
            if selection == 'e':
                return attempted and all_successful
            else:
                sleep(0.5)
                if config.debug_mode:
                    print("simulation mode - flashing disabled")
                    continue
                attempted = True
                success = os.system(first_attempt) == 0
                if not success:
                    print(f"{Bcolors.YELLOW}Unsuccessful flashing - trying with new bootloader{Bcolors.ENDC}")
                    print("Push reset button after seeing some characters below")
                    sleep(2)
                    success = os.system(second_attempt) == 0
                all_successful = success and all_successful
                print("Node - flashed" if success else "Node - not flashed, both bootloaders failed")

    while True:
        first_flash_select = """
        {bold}
        After selecting right port you will be asked to manually push
        reset button on each node according to instructions on the screen.

        After flashing last node for the first time hit 'e' to exit.

        Will you flash your nodes for the first time via UART (on PCB) 
        or using USB* port? [default: UART]

     {green}1 - UART (port ttyAMA0 - default){endc}{bold}

            2 - UART (port ttyS0 - try in case of errors)

            3 - USB (node connected to Pi's USB port)

            4 - Custom port selection

    {yellow}e - Exit{endc} 


""".format(green=Bcolors.GREEN_S, yellow=Bcolors.YELLOW_S, bold=Bcolors.BOLD, endc=Bcolors.ENDC)
        port_selection = input(first_flash_select)
        if port_selection == '1':
            success = flash_node_first_time('ttyAMA0')
        elif port_selection == '2':
            success = flash_node_first_time('ttyS0')
        elif port_selection == '3':
            usb_msg = """
    You are about to attempt first time firmware flashing via Pi's USB port.
    Node has to be ONLY device connected to Raspberry's USB 
    or connected to port named 'USB0'.
    Note that Arduino has to be DISCONNECTED from the PCB during the operation."""

            print(usb_msg)
            input("\n\tHit Enter when you will be ready ")
            success = flash_node_first_time('ttyUSB0')
        elif port_selection == '4':
            custom_port_selected = str(input("\n\tEnter custom port name here: "))
            success = flash_node_first_time(custom_port_selected)
        elif port_selection == 'e':
            break
        else:
            print("\n\tType: 'UART' or 'USB'\n\t")
            continue
        break
    print("FIRMWARE FLASHING - DONE" if success else "Flashing session ended without all nodes flashed")
    sleep(2)
    return success


def show_i2c_devices(config):
    while True:
        clear_the_screen()
        try:
            bus_number = config.i2c_bus_number
        except AttributeError:
            bus_number = 1  # defaulting to "1" cause Raspberry Pi uses it; in case of older json with no i2c_bus key
        detected_i2c_devices = os.popen(f"i2cdetect -y {bus_number}").read()
        print(f"\n\t{Bcolors.BOLD}Devices found on the {Bcolors.UNDERLINE}I2C bus {bus_number}{Bcolors.ENDC}:\n")
        print(Bcolors.BOLD)
        print(detected_i2c_devices)
        print(Bcolors.ENDC)
        # done that way because of the way how python is reading/converting hex numbers
        # and how raspberry is reporting addresses
        # space after an address is needed so line "number" is not being read as an address by mistake
        nodes_found = 0
        print("Nodes detected:")
        # don't change below to 'elif' - each node is a separate instance of "found"
        if '08 ' in detected_i2c_devices:
            print(f"Node 1 found")
            nodes_found += 1
        if '0a ' in detected_i2c_devices:
            print(f"Node 2 found")
            nodes_found += 1
        if '0c ' in detected_i2c_devices:
            print(f"Node 3 found")
            nodes_found += 1
        if '0e ' in detected_i2c_devices:
            print(f"Node 4 found")
            nodes_found += 1
        if '10 ' in detected_i2c_devices:
            print(f"Node 5 found")
            nodes_found += 1
        if '12 ' in detected_i2c_devices:
            print(f"Node 6 found")
            nodes_found += 1
        if '14 ' in detected_i2c_devices:
            print(f"Node 7 found")
            nodes_found += 1
        if '16 ' in detected_i2c_devices:
            print(f"Node 8 found")
            nodes_found += 1

        if nodes_found == 0:
            print(f"{Bcolors.RED}\nNo nodes detected{Bcolors.ENDC}")
            print(f"\n{Bcolors.UNDERLINE}Note: nodes have to be programmed before being discoverable\n\n{Bcolors.ENDC}")
        else:
            print(f"\n{Bcolors.GREEN}Detected nodes: {nodes_found}{Bcolors.ENDC}\n\n")

        if '76 ' in detected_i2c_devices or '77 ' in detected_i2c_devices:
            bme_found_flag = True
        else:
            bme_found_flag = False

        possible_ina_addr = ['40 ', '41 ', '43 ', '44 ']
        for item in possible_ina_addr:
            if item in detected_i2c_devices:
                ina_found_flag = True
                break
        else:
            ina_found_flag = False

        if bme_found_flag or ina_found_flag:
            print("\nSensors found: ")
            if bme_found_flag:
                print(f"{Bcolors.GREEN}BME sensor 280 found{Bcolors.ENDC}")
            if ina_found_flag:
                print(f"{Bcolors.GREEN}INA sensor 219 found{Bcolors.ENDC}")
        else:
            print("No additional sensors found")

        possible_rtc_addr = ['68 ', 'UU ', '50 ', '51 ', '52 ', '53 ', '54 ', '55 ', '56 ', '57 ']
        for item in possible_rtc_addr:
            if item in detected_i2c_devices:
                rtc_found_flag = True
                break
        else:
            rtc_found_flag = False

        if rtc_found_flag:
            print(f"{Bcolors.GREEN}\n\nRTC (DS3231 or PCF8523 or DS1307) found{Bcolors.ENDC}")
        else:
            print("\n\nNo RTC found")

        possible_oled_addr = ['3c']  # possible other oled screens addresses
        for item in possible_oled_addr:
            if item in detected_i2c_devices:
                oled_found_flag = True
                break
        else:
            oled_found_flag = False

        if oled_found_flag:
            print(f"{Bcolors.GREEN}\n\nOLED screen found{Bcolors.ENDC}")
        else:
            print("\n\nNo OLED screen found")

        print(Bcolors.ENDC)
        print(f"\n\n\t{Bcolors.RED}Press 'e' to exit to menu {Bcolors.ENDC}or hit 'Enter' to refresh")
        selection = input("\n")
        if selection == 'e':
            break


def firmware_info(config):
    while True:
        clear_the_screen()
        logo_top(config.debug_mode)
        print(f"\n\n")
        show_firmware = []
        with open(f'/home/{config.user}/RH_Install-Manager/firmware/current_api_levels.txt', 'r') as firmware_file:
            for line in firmware_file:
                show_firmware.append(f"\t\t{line}")

        firmware_output = ('\n\t\t'.join(show_firmware))
        print(f"{Bcolors.BOLD}{firmware_output}{Bcolors.ENDC}")
        selection = input(f"\n\n\t\t{Bcolors.BOLD}{Bcolors.GREEN}Exit by typing 'e'{Bcolors.ENDC}\t")
        if selection == 'e':
            break


def flashing_menu(config):
    while True:
        clear_the_screen()
        logo_top(config.debug_mode)
        node_menu = """\n

                          {rmh}FLASHING MENU{endc}{bold}{red}(for Arduino-based PCBs){endc}


       {green}{bold}1 - Flash each node automatically{endc}{bold}

                    2 - Flash nodes individually

                    3 - First time flashing

                    4 - Show I2C connected devices
                    
                    5 - Show firmware info 

            {yellow}e - Exit to main menu{endc}\n
            """.format(bold=Bcolors.BOLD_S, green=Bcolors.GREEN_S, yellow=Bcolors.YELLOW_S,
                       endc=Bcolors.ENDC, red=Bcolors.RED, underline=Bcolors.UNDERLINE_S,
                       rmh=Bcolors.RED_MENU_HEADER)
        print(node_menu)
        sleep(0.1)
        selection = input("")
        if selection == '1':
            all_nodes_flash(config)
        elif selection == '2':
            node_selection_menu(config)
        elif selection == '3':
            first_flashing(config)
        elif selection == '4':
            show_i2c_devices(config)
        elif selection == '5':
            firmware_info(config)
        elif selection == 'custom':  # hidden option TODO remove?
            all_nodes_flash(config)
        elif selection == 'e':
            break


def main():
    config = rhim_load_config()
    flashing_menu(config)


if __name__ == "__main__":
    main()
