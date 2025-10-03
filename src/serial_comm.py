# src/serial_comm.py
from __future__ import annotations
import serial
import time
from serial.tools import list_ports
from typing import List, Optional, Tuple

def _parse_status_block(text: str) -> dict:
    """
    parse the device status reply into a dict.
    - trims junk (nulls), keeps only lines between 'start' and 'end'
    - keeps keys exactly as reported by the device
    - converts numeric values (int/float) where possible
    """
    clean = text.replace("\x00", "")
    lines = [ln.strip() for ln in clean.splitlines() if ln.strip()]

    inside = False
    kv_pairs: list[tuple[str, str]] = []
    for ln in lines:
        up = ln.upper()
        if up == "START":
            inside = True
            continue
        if up == "END":
            break
        if not inside:
            continue
        if "=" in ln:
            k, v = ln.split("=", 1)
            kv_pairs.append((k.strip(), v.strip()))

    status: dict = {}
    for k, v in kv_pairs:
        # try to coerce values
        try:
            val = float(v)
            if val.is_integer():
                val = int(val)
        except Exception:
            try:
                val = int(v)
            except Exception:
                val = v
        status[k] = val

    return status

def list_available_ports() -> List[str]:
    """
    return a list of available serial port device names.
    """
    # all ui code should call this instead of accessing serial.tools.list_ports directly
    return [p.device for p in serial.tools.list_ports.comports()]

class PowerSupplyCommunicator:
    def __init__(self, baudrate=9600,  timeout: float = 0.05) -> None:
        # self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self._ser : Optional[serial.Serial] = None
        self.last_status: dict | None = None


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
        self._ser.flush()
        # optional short wait for device to generate a reply
        if wait_s > 0:
            time.sleep(wait_s)
        return None
        
    def query_status(self) -> dict:
        """
        send 'fs' to the device and read until 'END', then parse into a dict.
        """
        if not self._ser or not self.is_connected():
            raise ConnectionError("serial port not connected")
        assert self._ser is not None

        self._ser.reset_input_buffer()
        self._ser.reset_output_buffer()
        self._ser.write(b"FS\r\n")
        self._ser.flush()

        """
        make the port timeout very short so each read only waits a tiny bit
        if nothing comes, we quickly try again until we see the END line
        or until our overall timer runs out. this prevents the program from
        freezing for seconds if the device is slow, then we put the old timeout back
        """

        # an overall budget a bit above my full-frame time (I observed ~180–220 ms)
        overall_budget_s = 0.40  # 400 ms is snappy but tolerant
        deadline = time.monotonic() + overall_budget_s

        # temporarily shorten serial timeouts so readline() can't block for seconds
        orig_timeout = self._ser.timeout
        orig_ib_to = getattr(self._ser, "inter_byte_timeout", None)

        # collect lines until we hit 'END' or timeout
        lines: list[str] = []
        try:
            # per-line read timeout; keep very small so the while-loop cadence controls total time
            self._ser.timeout = 0.06
            try:
                self._ser.inter_byte_timeout = 0.02  # type: ignore[attr-defined]
            except Exception:
                pass

            while time.monotonic() < deadline:
                raw = self._ser.readline()
                if not raw:
                    # no line yet: keep looping until overall deadline
                    continue
                line = raw.decode(errors="ignore")
                lines.append(line)
                if line.strip().upper() == "END":
                    break

        finally:
            # restore original timeouts
            self._ser.timeout = orig_timeout
            try:
                if orig_ib_to is not None:
                    self._ser.inter_byte_timeout = orig_ib_to  # type: ignore[attr-defined]
            except Exception:
                pass

        raw_text = "".join(lines)
        parsed = _parse_status_block(raw_text)
        self.last_status = parsed
        return parsed

def find_com_port_by_sn(target_serial, baudrate: int = 9600, timeout: float = 1.5) -> str | None:
    """
    connect to each com port, call query_status() to read + parse once,
    and match 'SERIAL NUMBER' to target_serial. sends no commands here directly.
    """
    psu = PowerSupplyCommunicator(baudrate=baudrate, timeout=timeout)

    for p in list_ports.comports():
        port = p.device
        print(f"\n--- probing {port} ---")
        try:
            psu.connect(port)
            # query_status sends 'fs' internally via send_command
            data = psu.query_status()
            sn = data.get("SERIAL NUMBER")
            print(f"status: {data}")
            if sn is not None and str(sn).strip() == str(target_serial).strip():
                print(f"match found on {port}")
                return port
        except Exception as e:
            print(f"probe error on {port}: {e}")
        finally:
            # release the port before trying the next one
            try:
                psu.disconnect()
            except Exception:
                pass

    return None
