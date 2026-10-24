from time import sleep
from modules import rhim_load_config, Bcolors


def com_init(bus_number):
    error_msg = """
    SMBus(1) - error\nI2C communication doesn't work properly
    Check if I2C interface is enabled with 'sudo raspi-config'
    May try manually install smbus with 'sudo apt install python3-smbus'
    """
    try:
        try:
            # noinspection PyUnresolvedReferences
            from smbus2 import SMBus
        except ImportError:
            # noinspection PyUnresolvedReferences
            from smbus import SMBus  # for legacy OSes
        return SMBus(bus_number)
    except Exception as error:
        print(error_msg)
        print(error)
        raise


def reset_gpio_pin(gpio_reset_pin):
    try:
        # noinspection PyUnresolvedReferences
        import RPi.GPIO as GPIO
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)  # Use BCM pin numbering
        GPIO.setup(gpio_reset_pin, GPIO.OUT, initial=GPIO.HIGH)
        GPIO.output(gpio_reset_pin, GPIO.HIGH)
        sleep(0.1)
        GPIO.output(gpio_reset_pin, GPIO.LOW)
        print("gpio pin reset")
        sleep(0.1)
        GPIO.output(gpio_reset_pin, GPIO.HIGH)
        sleep(0.1)
    except Exception as error:
        print("GPIO reset failed: {}".format(error))
        raise


def prepare_mate_node(addr):
    def calculate_checksum(data):
        checksum = sum(data) & 0xFF
        return checksum

    config = rhim_load_config()
    try:
        bus_number = config.i2c_bus_number  # check with "ls /dev/ | grep i2c" (Raspberry Pi - 1; Banana Pi - 0)
    except AttributeError:
        bus_number = 1  # defaulting to "1" cause Raspberry Pi uses it; in case of older json with no i2c_bus key
    bus = com_init(bus_number)
    sleep_amt = 1
    on, off = [1], [0]
    reset_mate_node_command = 0x79
    on.append(calculate_checksum(on))
    off.append(calculate_checksum(off))
    sleep(sleep_amt)
    try:
        bus.write_i2c_block_data(addr, reset_mate_node_command, on)
        print("on command sent")
        sleep(sleep_amt)
        bus.write_i2c_block_data(addr, reset_mate_node_command, off)
        print("off command sent")
        sleep(sleep_amt)
        bus.write_i2c_block_data(addr, reset_mate_node_command, on)
        print("on command sent")
        sleep(0.2)
    except Exception as error:
        print(f"\n{Bcolors.RED}I2C reset failed - check bus number and wiring: {error}{Bcolors.ENDC}\n")
        raise
    finally:
        bus.close()


def main():
    print("Use file nodes_flash.py as a opening file instead")


if __name__ == "__main__":
    main()
