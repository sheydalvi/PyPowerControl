# src/serial_comm.py
from __future__ import annotations
import serial
import time
from serial.tools import list_ports
from typing import List, Optional, Tuple

def list_available_ports() -> List[str]:
    """
    return a list of available serial port device names.
    """
    # all ui code should call this instead of accessing serial.tools.list_ports directly
    return [p.device for p in serial.tools.list_ports.comports()]


def _clean_response(raw: bytes) -> str:
    """
    clean device responses:
    - decode as ascii (fallback to latin-1 if needed)
    - strip nulls and surrounding whitespace/newlines
    """
    try:
        text = raw.decode("ascii", errors="ignore")
    except Exception:
        text = raw.decode("latin-1", errors="ignore")
    # remove any embedded nulls the device might emit
    text = text.replace("\x00", "")
    return text.strip()

def find_device_port(
    probe_command: str = "FS",
    expected_token: Optional[str] = None,
    read_timeout_s: float = 0.2,
) -> Optional[str]:
    """
    scan ports and send a probe command (default 'fs') to find the right device.
    if expected_token is provided, we only accept a port whose response contains it.
    returns the matching port string or none.
    """
    for port in list_available_ports():
        try:
            with serial.Serial(port=port, baudrate=9600, timeout=read_timeout_s) as s:
                # always send with newline here to match device parser
                s.write((probe_command + "\n").encode("ascii"))
                time.sleep(0.05)  # small settle
                raw = s.read(1024)
                resp = _clean_response(raw)
                if not expected_token:
                    # any non-empty response qualifies if no token is specified
                    if resp:
                        return port
                else:
                    if expected_token in resp:
                        return port
        except Exception:
            # ignore errors and keep scanning others
            continue
    return None


class PowerSupplyCommunicator:
    def __init__(self, baudrate=9600,  timeout: float = 0.05) -> None:
        # self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self._ser : Optional[serial.Serial] = None

    def connect(self, port: str) -> None:
        self.disconnect()
        self._ser = serial.Serial(port=port, baudrate=self.baudrate, timeout=self.timeout)

    def disconnect(self) -> None:
        if self._ser and self._ser.is_open:
            try:
                self._ser.close()
            finally:
                self._ser = None

    def is_connected(self) -> bool:
        return bool(self._ser and self._ser.is_open)

    def send_command(self, cmd: str, wait_s: float = 0.05) -> str:
        if not self._ser or not self.is_connected():
            raise ConnectionError("serial port not connected")
        assert self._ser is not None
        # always append newline here so callers don't have to remember
        payload = (cmd + "\n").encode("ascii")
        self._ser.reset_input_buffer()
        self._ser.write(payload)
        # optional short wait for device to generate a reply
        if wait_s > 0:
            time.sleep(wait_s)
        raw = self._ser.read(1024)
        return _clean_response(raw)

def find_com_port_by_sn(target_serial, baudrate=9600, timeout=2):
    ports = list_ports.comports()
    print(f"Scanning ports for device with serial: {target_serial}")

    for port in ports:
        print(f"\n--- Probing {port.device} ---")
        try:
            ser = serial.Serial(port.device, baudrate, timeout=timeout)
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

def query_status(self) -> str:
    return self.send_command("FS")
