# src/serial_comm.py
import serial
import time
from serial.tools import list_ports


class PowerSupplyCommunicator:
    def __init__(self, port, baud_rate=9600, timeout=2):
        self.port = port
        self.baud_rate = baud_rate
        self.timeout = timeout
        self.ser = None

    def connect(self):
        try:
            self.ser = serial.Serial(self.port, self.baud_rate, timeout=self.timeout)
            time.sleep(1)  # Allow time to establish connection
        except serial.SerialException as e:
            print(f"Failed to connect: {e}")
            raise

    def disconnect(self):
        if self.ser and self.ser.is_open:
            self.ser.close()

    def send_command(self, command):
        if not self.ser or not self.ser.is_open:
            raise ConnectionError("Serial port is not open.")

        self.ser.write(command.encode())
        time.sleep(0.5)  # Wait for device to respond
        response = self.ser.read_all().decode(errors='ignore')
        return response

def find_com_port_by_sf_response(target_serial, baud_rate=9600, timeout=2):
    ports = list_ports.comports()
    print(f"Scanning ports for device with serial: {target_serial}")

    for port in ports:
        print(f"\n--- Probing {port.device} ---")
        try:
            ser = serial.Serial(port.device, baud_rate, timeout=timeout)
            time.sleep(1)  # allow device to initialize

            ser.write(b"FS\n")
            time.sleep(0.5)
            response = ser.read_all().decode(errors='ignore')
            ser.close()
            print(f"Raw response from {port.device}:\n{response!r}")


            for line in response.splitlines():
                if "SERIAL NUMBER=" in line:
                    print(f"Found serial line: {line}")
                    serial_value = line.split("=")[-1].strip()
                    print(f"Extracted serial number: {serial_value}")
                    if serial_value == target_serial:
                        print(f" Match found on port {port.device}")
                        return port.device
                    else:
                        print(f"Serial number mismatch (expected {target_serial})")

        except Exception as e:
            print(f"Error probing {port.device}: {e}")
            continue

    return None
