# src/serial_comm.py
import serial
import time

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
