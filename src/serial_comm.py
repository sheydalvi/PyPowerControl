# main.py
from src.serial_comm import PowerSupplyCommunicator

def main():
    port = "COM3"        # Change this to your COM port
    baud_rate = 9600     # Match what you used in Termite

    psu = PowerSupplyCommunicator(port, baud_rate)
    psu.connect()

    try:
        command = "FS\r"  # Adjust line ending as needed
        response = psu.send_command(command)
        print("Response from power supply:", response)
    finally:
        psu.disconnect()

if __name__ == "__main__":
    main()
