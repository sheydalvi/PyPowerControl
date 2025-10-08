# src/serial_comm.py
from __future__ import annotations
import serial
import time
from serial.tools import list_ports
from typing import List, Optional, Tuple
import threading

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
        self._io_lock = threading.Lock()
        self.CMD_PROC_WAIT    = 0.10  # per-command processing delay
        self.GAP_POST_COMMAND = 0.25  # seconds after sending any command before next TX
        self.GAP_PRE_FROM_FS  = 0.18  # seconds before sending a command after FS


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


    def send_command(
        self,
        cmd: str,
        wait_s: float | None = None,
        post_quiet_s: float | None = None,
        pre_gap_from_rx_s: float | None = None) -> None:
        # fill per-instance defaults
        if wait_s is None:
            wait_s = self.CMD_PROC_WAIT
        if post_quiet_s is None:
            post_quiet_s = self.GAP_POST_COMMAND
        if pre_gap_from_rx_s is None:
            pre_gap_from_rx_s = self.GAP_PRE_FROM_FS

        if not self._ser or not self.is_connected():
            raise ConnectionError("serial port not connected")

        payload = (cmd + "\r\n").encode("ascii")
        with self._io_lock:
            # gap from last FS read completion
            gap = time.monotonic() - getattr(self, "last_rx_time", 0.0)
            if gap < pre_gap_from_rx_s:
                time.sleep(pre_gap_from_rx_s - gap)

            n = self._ser.write(payload)
            self._ser.flush()
            if n != len(payload):
                raise IOError(f"short write: {n}/{len(payload)} bytes")

            self.last_tx_cmd = cmd
            self.last_tx_time = time.monotonic()

            if wait_s > 0:
                time.sleep(wait_s)

            if post_quiet_s > 0:
                time.sleep(post_quiet_s)
            

    # add inside class PowerSupplyCommunicator in src/serial_comm.py
    def set_power(self, value: int) -> str:
        # clamp to device range 0700..1050
        if value < 700:
            value = 700
        elif value > 1050:
            value = 1050

        if not self.is_connected():
            raise ConnectionError("serial port not connected")

        # many supplies expect zero-padded 4-digit power command like P1234
        # if your device requires 'P=1234' instead, change the next line accordingly
        cmd = f"P={value:04d}"
        self.send_command(cmd, wait_s=0.08)  # brief wait so device can act
        return "OK"

        
    def query_status(self) -> dict:
        """
        send 'fs' to the device and read until 'END', then parse into a dict.
        """
        if not self._ser or not self.is_connected():
            raise ConnectionError("serial port not connected")
        assert self._ser is not None

        # self._ser.reset_input_buffer()
        # self._ser.reset_output_buffer()
        # self._ser.write(b"FS\r\n")
        # self._ser.flush()

        """
        make the port timeout very short so each read only waits a tiny bit
        if nothing comes, we quickly try again until we see the END line
        or until our overall timer runs out. this prevents the program from
        freezing for seconds if the device is slow, then we put the old timeout back
        """

        # an overall budget a bit above my full-frame time (I observed ~180–220 ms)
        overall_budget_s = 0.50  # 400 ms is snappy but tolerant
        deadline = time.monotonic() + overall_budget_s

        # temporarily shorten serial timeouts so readline() can't block for seconds
        orig_timeout = self._ser.timeout
        orig_ib_to = getattr(self._ser, "inter_byte_timeout", None)

        # collect lines until we hit 'END' or timeout
        lines: list[str] = []
        saw_start = False
        saw_end = False

        # take the lock for the full FS write+read
        with self._io_lock:
            # don’t throw away data from the device right before we ask for FS
            # (comment out the next line if your device *needs* a purge)
            # self._ser.reset_input_buffer()

            self._ser.write(b"FS\r\n")
            self._ser.flush()

            try:
                self._ser.timeout = 0.08
                try:
                    self._ser.inter_byte_timeout = 0.03  # type: ignore[attr-defined]
                except Exception:
                    pass

                while time.monotonic() < deadline:
                    raw = self._ser.readline()
                    if not raw:
                        continue
                    line = raw.decode(errors="ignore")
                    up = line.strip().upper()
                    if up == "START":
                        saw_start = True
                    elif up == "END":
                        saw_end = True
                        lines.append(line)
                        break
                    lines.append(line)
            finally:
                self._ser.timeout = orig_timeout
                try:
                    if orig_ib_to is not None:
                        self._ser.inter_byte_timeout = orig_ib_to  # type: ignore[attr-defined]
                except Exception:
                    pass

        raw_text = "".join(lines)
        parsed = _parse_status_block(raw_text)
        parsed["_FRAME_COMPLETE"] = bool(saw_start and saw_end)
        self.last_status = parsed
        self.last_rx_time = time.monotonic()  # finished consuming FS frame
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
