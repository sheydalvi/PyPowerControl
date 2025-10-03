# src/cgui.py
from __future__ import annotations
import customtkinter as ctk
from tkinter import messagebox
import tkinter as tk
from src.serial_comm import PowerSupplyCommunicator, list_available_ports, find_com_port_by_sn
import time

ctk.set_appearance_mode("System")  # options: "system", "dark", "light"
ctk.set_default_color_theme("blue")  # you can change this to "green", "dark-blue", etc.

COMMANDS: Dict[str, tuple[str, str]] = {
    "fan": ("C1", "C0"),
    "shutter": ("S1", "S0"),
    "lamp": ("L1", "L0"),
}

def command_for(name: str, state_on: bool) -> str:
    """
    map a boolean state to the proper device command string.
    """
    if name not in COMMANDS:
        raise KeyError(f"unknown command group '{name}'")
    on_cmd, off_cmd = COMMANDS[name]
    return on_cmd if state_on else off_cmd

class PowerSupplyGUI(ctk.CTk):
    """
    top-level application window that owns ui widgets and a communicator.
    """
    # inside PowerSupplyGUI


    def _set_busy(self, busy: bool) -> None:
        """
        show a wait cursor while busy; when done, restore hand cursor on buttons.
        """
        cursor = "wait" if busy else ""

        def all_widgets(root):
            stack = [root]
            while stack:
                w = stack.pop()
                yield w
                if hasattr(w, "winfo_children"):
                    stack.extend(w.winfo_children())

        try:
            if busy:
                # set wait cursor on everything
                for w in all_widgets(self):
                    try:
                        w.configure(cursor="wait")
                    except Exception:
                        pass
            else:
                # restore: hand on buttons, default on others
                for w in all_widgets(self):
                    try:
                        if isinstance(w, ctk.CTkButton):
                            w.configure(cursor="hand2")
                        else:
                            w.configure(cursor="")
                    except Exception:
                        pass
        except Exception:
            pass

    def __init__(self) -> None:
        super().__init__()

        # basic window setup
        self.title("power supply controller")
        self.geometry("720x460")
        # optional: set default theme / appearance
        # ctk.set_appearance_mode("system")  # or "light" / "dark"
        # ctk.set_default_color_theme("blue")  # "blue", "green", "dark-blue"

        # communicator (hardware driver)
        self.psu = PowerSupplyCommunicator()
        # prevents sending commands when we flip switches programmatically
        self._syncing_from_status = False
        # ===== top bar: port selection and connect/disconnect =====
        auto_row = ctk.CTkFrame(self)
        auto_row.pack(fill="x", padx=12, pady=(0, 8))

        ctk.CTkLabel(auto_row, text="device serial").pack(side="left", padx=(8, 6))
        self.serial_var = tk.StringVar(value="")
        self.serial_entry = ctk.CTkEntry(auto_row, textvariable=self.serial_var, width=180)
        self.serial_entry.pack(side="left", padx=6)

        self.auto_btn = ctk.CTkButton(auto_row, text="auto connect", command=self.auto_connect, width=120)
        self.auto_btn.pack(side="left", padx=8)

        
        self.start_auto_btn = ctk.CTkButton(auto_row, text="start auto-query", command=self.start_auto_query, width=120)
        self.start_auto_btn.pack(side="left", padx=6)

        self.stop_auto_btn = ctk.CTkButton(auto_row, text="stop auto-query", command=self.stop_auto_query, width=120)
        self.stop_auto_btn.pack(side="left", padx=6)


        top = ctk.CTkFrame(self)
        top.pack(fill="x", padx=12, pady=10)

        self.port_label = ctk.CTkLabel(top, text="port")
        self.port_label.pack(side="left", padx=(8, 6))

        # customtkinter provides ctk.CTkOptionMenu; we use it like a read-only combobox
        self.port_values: list[str] = []
        self.port_var = tk.StringVar(value="")
        self.port_menu = ctk.CTkOptionMenu(
            top,
            variable=self.port_var,
            values=self.port_values or ["<no ports>"],
            width=180,
        )
        self.port_menu.pack(side="left", padx=6)

        self.refresh_btn = ctk.CTkButton(top, text="refresh", command=self.refresh_ports, width=90)
        self.refresh_btn.pack(side="left", padx=6)

        self.connect_btn = ctk.CTkButton(top, text="connect", command=self.connect_to_selected, width=90)
        self.connect_btn.pack(side="left", padx=6)

        self.disconnect_btn = ctk.CTkButton(top, text="disconnect", command=self.disconnect, width=100)
        self.disconnect_btn.pack(side="left", padx=6)
 

        # ===== switches row =====
        switch_row = ctk.CTkFrame(self)
        switch_row.pack(fill="x", padx=12, pady=8)

        # note: customtkinter switches don't need explicit booleanvars, but using them makes state handling simple
        self.fan_var = tk.BooleanVar(value=False)
        self.shutter_var = tk.BooleanVar(value=False)
        self.lamp_var = tk.BooleanVar(value=False)

        self.fan_sw = ctk.CTkSwitch(
            switch_row,
            text="fan",
            variable=self.fan_var,
            command=lambda: self.handle_switch("fan", self.fan_var),
        )
        self.fan_sw.pack(side="left", padx=10)

        self.shutter_sw = ctk.CTkSwitch(
            switch_row,
            text="shutter",
            variable=self.shutter_var,
            command=lambda: self.handle_switch("shutter", self.shutter_var),
        )
        self.shutter_sw.pack(side="left", padx=10)

        self.lamp_sw = ctk.CTkSwitch(
            switch_row,
            text="lamp",
            variable=self.lamp_var,
            command=lambda: self.handle_switch("lamp", self.lamp_var),
        )
        self.lamp_sw.pack(side="left", padx=10)

        # ===== power controls =====
        power_row = ctk.CTkFrame(self)
        power_row.pack(fill="x", padx=12, pady=8)

        self.power_label = ctk.CTkLabel(power_row, text="power (0–9999)")
        self.power_label.pack(side="left", padx=(8, 6))

        self.power_var = tk.StringVar(value="0")
        self.power_entry = ctk.CTkEntry(power_row, textvariable=self.power_var, width=90)
        self.power_entry.pack(side="left", padx=6)

        self.set_btn = ctk.CTkButton(power_row, text="set", command=self.set_power, width=80)
        self.set_btn.pack(side="left", padx=6)

        self.status_btn = ctk.CTkButton(power_row, text="status", command=self.query_status_handler, width=90)
        self.status_btn.pack(side="left", padx=6)


        # ===== output log =====
        out_frame = ctk.CTkFrame(self)
        out_frame.pack(fill="both", expand=True, padx=12, pady=10)

        self.output = ctk.CTkTextbox(out_frame, wrap="word")
        self.output.pack(fill="both", expand=True, padx=8, pady=8)

        # initialize available ports
        self.refresh_ports()

        # graceful close
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    # ===== ui helpers =====

    def start_auto_query(self) -> None:
        # start periodic queries once every second
        self._auto_query_running = True
        self._auto_query_loop()

    def stop_auto_query(self) -> None:
        # stop the periodic queries
        self._auto_query_running = False

    def _auto_query_loop(self) -> None:
        if not getattr(self, "_auto_query_running", False):
            return
        if not self.ensure_connected():
            self._auto_query_running = False
            return
        try:
            t0 = time.monotonic()
            data = self.psu.query_status()
            dt = (time.monotonic() - t0) * 1000
            self.log(f"FS reply in {dt:.1f} ms: {data}")
            if data:
                self._apply_status_to_switches(data)
        except Exception as e:
            messagebox.showerror("auto query error", str(e))
            self._auto_query_running = False
            return
        self.after(1000, self._auto_query_loop)


    def log(self, text: str) -> None:
        """
        append text to the output box.
        """
        self.output.insert("end", text + "\n")
        self.output.see("end")

    def _set_port_values(self, ports: list[str]) -> None:
        """
        update the option menu's values safely (fallback when empty).
        """
        self.port_values = ports[:]  # store a copy
        if not self.port_values:
            # when no ports found, present a disabled-looking placeholder
            display_values = ["<no ports>"]
            self.port_var.set("<no ports>")
        else:
            display_values = self.port_values
            # select first port if none selected
            if self.port_var.get() not in self.port_values:
                self.port_var.set(self.port_values[0])
        # customtkinter optionmenu updates values via set_values
        self.port_menu.configure(values=display_values)

    def refresh_ports(self) -> None:
        """
        populate the port dropdown using serial_comm.list_available_ports.
        """
        try:
            ports = list_available_ports()
        except Exception as e:
            self._set_port_values([])
            messagebox.showerror("ports error", str(e))
            return
        self._set_port_values(ports)

    def connect_to_selected(self) -> None:
        """
        connect button handler: uses the selected port from the dropdown.
        """
        port = self.port_var.get().strip()
        if not port or port == "<no ports>":
            messagebox.showwarning("connect", "please refresh and pick a port first")
            return
        try:
            self.psu.connect(port)
            self.log(f"connected to {port}")
            # start auto-query by default
            self.start_auto_query()
        except Exception as e:
            messagebox.showerror("connect failed", str(e))

    def auto_connect(self) -> None:
        """
        run auto-detect on the ui thread but show a busy cursor.
        note: ui will be unresponsive during the scan (by design).
        """
        target = self.serial_var.get().strip()
        if not target:
            messagebox.showwarning("auto connect", "enter a device serial first")
            return

        # turn on busy state
        self._set_busy(True)
        self.log(f"auto connect: scanning ports for serial '{target}'...")

        try:
            # use whatever attribute names you chose
            baud = getattr(self.psu, "baudrate", 9600)
            timeout = getattr(self.psu, "timeout", 2)

            # call your existing finder directly (blocking)
            port = find_com_port_by_sn(target_serial=target, baudrate=baud, timeout=timeout)

            if not port:
                self.log("auto connect: device not found")
                return

            # connect and reflect in ui
            self.psu.connect(port)
            self.port_var.set(port)
            self.log(f"auto connect: connected to {port}")
            self.start_auto_query()


        except Exception as e:
            from tkinter import messagebox
            messagebox.showerror("auto connect error", str(e))

        finally:
            # always restore cursor and buttons
            self._set_busy(False)

    def disconnect(self) -> None:
        """
        disconnect button handler.
        """
        try:
            self.psu.disconnect()
            self.log("disconnected")
        except Exception as e:
            messagebox.showerror("disconnect failed", str(e))

    def ensure_connected(self) -> bool:
        """
        guard to avoid sending when not connected.
        """
        if not self.psu.is_connected():
            messagebox.showwarning("not connected", "please connect to a port first")
            return False
        return True

    def _confirm_then_resume(self, name: str, var: tk.BooleanVar, desired: bool,
                            status_key: str, was_running: bool) -> None:
        # retry a few quick confirms so we don't revert on a stale read
        # total confirm window ~ 350–450 ms which still feels instant to the user
        try:
            def as_bool(v):
                try:
                    return bool(int(v))
                except Exception:
                    return bool(v)

            attempts = 1          # number of confirm reads
            spacing_ms = 0      # delay between reads
            success = False
            last_actual = None

            for i in range(attempts):
                data = self.psu.query_status()
                actual = as_bool(data.get(status_key))
                last_actual = actual

                # log once for visibility
                if i == 0:
                    self.log(f"confirm {status_key}={int(actual)}")

                if actual == desired:
                    # device reached requested state within the grace window
                    self._apply_status_to_switches(data)
                    success = True
                    break

                # not yet matched, wait a bit and try again
                self.update_idletasks()
                self.after(spacing_ms)
                self.update_idletasks()

            if not success:
                # after grace window it still disagrees, revert immediately
                self._syncing_from_status = True
                try:
                    var.set(last_actual if last_actual is not None else not desired)
                finally:
                    self._syncing_from_status = False

        except Exception:
            # on any read error, fail fast and revert so ui never lingers wrong
            var.set(not desired)

        finally:
            if was_running:
                self.after(0, self.start_auto_query)

    
    def handle_switch(self, name: str, var: tk.BooleanVar) -> None:
        if getattr(self, "_syncing_from_status", False):
            return

        if not self.ensure_connected():
            var.set(not var.get())
            return

        desired = var.get()
        key_map = {"fan": "COOL", "lamp": "LAMP", "shutter": "SHUTTER"}
        status_key = key_map.get(name, name.upper())

        was_running = getattr(self, "_auto_query_running", False)
        self._auto_query_running = False

        try:
            cmd = command_for(name, desired)
            self.psu.send_command(cmd, wait_s=0.06)
            self.log(f"> {cmd}")
        except Exception as e:
            var.set(not desired)
            messagebox.showerror("command failed", str(e))
            if was_running:
                self.after(0, self.start_auto_query)
            return

        # schedule the confirm via helper
        self.after(320, lambda: self._confirm_then_resume(name, var, desired, status_key, was_running))




    def _apply_status_to_switches(self, status: dict) -> None:
        """
        set ui switches based on device status without firing commands.
        device labels are used as-is: 'COOL', 'LAMP', 'SHUTTER' (0/1).
        """
        def as_bool(val):
            try:
                return bool(int(val))
            except Exception:
                return False

        # start guarded section: flips won't trigger handle_switch
        self._syncing_from_status = True
        try:
            if "COOL" in status:
                self.fan_var.set(as_bool(status["COOL"]))
            if "LAMP" in status:
                self.lamp_var.set(as_bool(status["LAMP"]))
            if "SHUTTER" in status:
                self.shutter_var.set(as_bool(status["SHUTTER"]))
        finally:
            self._syncing_from_status = False


    def set_power(self) -> None:
        """
        parse the entry, clamp if needed, and call the communicator helper.
        """
        if not self.ensure_connected():
            return
        try:
            value = int(self.power_var.get())
        except ValueError:
            messagebox.showwarning("invalid power", "enter an integer 0..9999")
            return
        try:
            resp = self.psu.set_power(value)
            self.log(f"> P={value:04d}\n< {resp}")
        except Exception as e:
            messagebox.showerror("set power failed", str(e))

    def query_status_handler(self) -> None:
        if not self.ensure_connected():
            return
        try:
            data = self.psu.query_status()
            # self.log("> FS")
            for k, v in data.items():
                self.log(f"{k}: {v}")
            # reflect device state on switches
            self._apply_status_to_switches(data)
        except Exception as e:
            from tkinter import messagebox
            messagebox.showerror("query status failed", str(e))

    def on_close(self) -> None:
        """
        clean shutdown on window close.
        """
        try:
            self.psu.disconnect()
        finally:
            self.destroy()