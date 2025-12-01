# src/cgui.py
from __future__ import annotations
import customtkinter as ctk
from tkinter import messagebox
import tkinter as tk
from src.serial_comm import PowerSupplyCommunicator, list_available_ports, find_com_port_by_sn
import time
import json
import os
from datetime import datetime
from PIL import Image, ImageTk


ctk.set_appearance_mode("light")  # options: "system", "dark", "light"
ctk.set_default_color_theme("blue")  # you can change this to "green", "dark-blue", etc.

COMMANDS: Dict[str, tuple[str, str]] = {
    "fan": ("C1", "C0"),
    "shutter": ("S1", "S0"),
    "lamp": ("L1", "L0"),
}

def read_config(filename="config.json"):
    """Read configuration from a JSON file and return as a dict."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    filepath = os.path.join(script_dir, filename)

    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                print("Error: config.json is not valid JSON.")
    else:
        print(f"File not found: {filepath}")
    return {}
config = read_config("config.json")


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
        self.geometry("600x800")
        # optional: set default theme / appearance
        # ctk.set_appearance_mode("system")  # or "light" / "dark"
        # ctk.set_default_color_theme("blue")  # "blue", "green", "dark-blue"

        # communicator (hardware driver)
        self.psu = PowerSupplyCommunicator()
        # prevents sending commands when we flip switches programmatically
        self._syncing_from_status = False
        # monotonic timestamp until which auto-query should not run
        self._busy_until = 0.0 
        # ===== top bar: port selection and connect/disconnect =====
        auto_row = ctk.CTkFrame(self)
        auto_row.pack(fill="x", padx=12, pady=(0, 8))

        print("Loaded configuration:", config)
        ctk.CTkLabel(auto_row, text="device serial").pack(side="left", padx=(8, 6), pady=5)
        # self.serial_var = tk.StringVar(value="")
        # self.serial_entry = ctk.CTkEntry(auto_row, textvariable=self.serial_var, width=180)
        # self.serial_entry.pack(side="left", padx=6)
        self.serial_var = tk.StringVar(value=config["sn"])

        self.serial_entry = ctk.CTkEntry(auto_row, textvariable=self.serial_var, width=180)
        self.serial_entry.pack(side="left", padx=5, pady=5)



        self.auto_btn = ctk.CTkButton(auto_row, text="Find PS", command=self.auto_connect, width=90)
        self.auto_btn.pack(side="left", padx=5, pady=5)

        
        self.start_auto_btn = ctk.CTkButton(auto_row, text="syncing", command=self.start_auto_query, width=90)
        self.start_auto_btn.pack(side="left", padx=5, pady=5)

        self.stop_auto_btn = ctk.CTkButton(auto_row, text="pause sync", command=self.stop_auto_query, width=90)
        self.stop_auto_btn.pack(side="left", padx=5, pady=5)


        top = ctk.CTkFrame(self)
        top.pack(fill="x", padx=12, pady=10)

        self.port_label = ctk.CTkLabel(top, text="port")
        self.port_label.pack(side="left", padx=(8, 6), pady=5)

        # customtkinter provides ctk.CTkOptionMenu; we use it like a read-only combobox
        self.port_values: list[str] = []
        self.port_var = tk.StringVar(value="")
        self.port_menu = ctk.CTkOptionMenu(
            top,
            variable=self.port_var,
            values=self.port_values or ["<no ports>"],
            width=180,
        )
        self.port_menu.pack(side="left", padx=6, pady=5)

        self.refresh_btn = ctk.CTkButton(top, text="refresh", command=self.refresh_ports, width=90)
        self.refresh_btn.pack(side="left", padx=6, pady=5)

        self.connect_btn = ctk.CTkButton(top, text="connect", command=self.connect_to_selected, width=90)
        self.connect_btn.pack(side="left", padx=6, pady=5)

        self.disconnect_btn = ctk.CTkButton(top, text="disconnect", command=self.disconnect, width=100)
        self.disconnect_btn.pack(side="left", padx=6, pady=5)
        ###

        # ===== switches row =====
        switch_row = ctk.CTkFrame(self)
        switch_row.pack(fill="x", padx=12, pady=8)

        # upload images as icons
        def img(filename):
            return tk.PhotoImage(file=os.path.join(os.path.dirname(__file__), filename))

        # Load your images
        self.fan_img = img("fan_color.png")
        self.lamp_img = img("lamp_color.png")
        self.shutter_img = img("shutter.png")

        center_container = ctk.CTkFrame(switch_row)
        center_container.pack(side="right", padx=5, pady=5) 

        # Fan frame
        fan_frame = ctk.CTkFrame(center_container)
        fan_frame.pack(side="left", padx=5, pady=5)

        self.fan_icon_label = ctk.CTkLabel(fan_frame, image=self.fan_img, text='FAN', compound='bottom', font=("Arial", 10))
        self.fan_icon_label.pack(pady=5) 

        # note: customtkinter switches don't need explicit booleanvars, but using them makes state handling simple
        self.fan_var = tk.BooleanVar(value=False)

        self.fan_sw = ctk.CTkSwitch(
            fan_frame,
            text="",
            variable=self.fan_var,
            width=50,
            switch_width=50,
            command=lambda: self.handle_switch("fan", self.fan_var),
        )
        self.fan_sw.pack(pady=5)

        # Lamp frame
        lamp_frame = ctk.CTkFrame(center_container)
        lamp_frame.pack(side="left", padx=5, pady=5)

        self.lamp_icon_label = ctk.CTkLabel(lamp_frame, image=self.lamp_img, text='LAMP', compound='bottom', font=("Arial", 10))
        self.lamp_icon_label.pack(pady=5)

        self.lamp_var = tk.BooleanVar(value=False)

        self.lamp_sw = ctk.CTkSwitch(
            lamp_frame,
            text="",
            width=50,
            switch_width=50,
            variable=self.lamp_var,
            command=lambda: self.handle_switch("lamp", self.lamp_var),
        )
        self.lamp_sw.pack(pady=5)

        if config["HasShutter"] == 1:
            self.shutter_var = tk.BooleanVar(value=False)

            shutter_frame = ctk.CTkFrame(center_container)
            shutter_frame.pack(side="right", padx=5, pady=5)

            self.shutt_icon_label = ctk.CTkLabel(shutter_frame, image=self.shutter_img, text='SHUTTER', compound='bottom', font=("Arial", 10))
            self.shutt_icon_label.pack(pady=5)

            self.shutter_sw = ctk.CTkSwitch(
            shutter_frame,
            text="",
            width=50,
            switch_width=50,
            variable=self.shutter_var,
            command=lambda: self.handle_switch("shutter", self.shutter_var),
            )
            self.shutter_sw.pack(pady=5)

        # power frame
        power_frame = ctk.CTkFrame(switch_row)
        power_frame.pack(side="left", padx=20, pady=5)

        ctk.CTkLabel(power_frame, text='POWER %', font=("Arial", 16)).pack(pady=(5, 0))

        self.power_label = ctk.CTkLabel(power_frame, text="")
        self.power_label.pack(side="left", padx=(8, 6), pady=5)

        self.power_vardigit = tk.StringVar(value="0")
        self.power_entry = ctk.CTkEntry(power_frame, textvariable=self.power_vardigit, width=90)
        self.power_entry.bind("<Return>", self._on_power_edit_end)
        self.power_entry.pack(side="left", padx=6)

        self._editing_power = False
        self.power_entry.bind("<FocusIn>", self._on_power_edit_start)
        self.power_entry.bind("<FocusOut>", self._on_power_edit_end)
        self.power_entry.bind("<Return>", self._on_power_commit) 

        self.set_btn = ctk.CTkButton(power_frame, text="set", command=self.set_power, width=80)
        self.set_btn.pack(side="right", padx=6, pady=5)

        # self.status_btn = ctk.CTkButton(power_row, text="status", command=self.query_status_handler, width=90)
        # self.status_btn.pack(side="right", padx=6)

        # ===== feedback =====
        feedback_frame = ctk.CTkFrame(self, corner_radius=12, fg_color=("gray90", "gray13"))
        feedback_frame.pack(fill="x", padx=12, pady=12)

        # StringVars for live values
        self.voltage_var = ctk.StringVar(value="0.00 V")
        self.current_var = ctk.StringVar(value="0.00 A")
        self.power_var = ctk.StringVar(value="0.00 W")
        self.lamplife_var = ctk.StringVar(value="0 min")

        title = ctk.CTkLabel(
            feedback_frame,
            text="System Feedback",
            font=("Roboto Mono", 14, "bold")
        )
        title.pack(pady=(10, 5))

        # separator line
        ctk.CTkFrame(
            feedback_frame,
            height=2,
            fg_color=("gray70", "gray30")
        ).pack(fill="x", padx=10, pady=(0, 15))

        # ---- row of metrics ----
        row = ctk.CTkFrame(feedback_frame, fg_color="transparent")
        row.pack(fill="x", pady=10)

        header_font = ("Roboto Mono", 14, "bold")
        value_font = ("Roboto Mono", 14, "bold")

        def block(parent, label, var):
            f = ctk.CTkFrame(parent, corner_radius=6, fg_color=("gray85", "gray20"))
            f.grid_propagate(False)
            f.configure(width=140, height=80)

            ctk.CTkLabel(f, text=label, font=header_font).pack(pady=(5, 0))
            ctk.CTkLabel(f, textvariable=var, font=value_font).pack()
            return f

        block(row, "  Voltage  ", self.voltage_var).grid(row=0, column=0, padx=10)
        block(row, "  Current  ", self.current_var).grid(row=0, column=1, padx=10)
        block(row, "  Power  ",   self.power_var).grid(row=0, column=2, padx=10)
        block(row, "  Lamp Age  ", self.lamplife_var).grid(row=0, column=3, padx=10)


        # make all columns expand evenly
        for i in range(4):
            row.grid_columnconfigure(i, weight=1)


        # ===== output log =====
        if config["log"] == 1:
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
            # skip polling during command quiet windows
        if time.monotonic() < getattr(self, "_busy_until", 0.0):
            self.after(50, self._auto_query_loop)  # check again soon
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
    
    def pause_auto_query(self, ms: int):
        was_running = getattr(self, "_auto_query_running", False)
        self._auto_query_running = False
        if was_running:
            # resume and immediately restart loop after delay
            self.after(ms, lambda: [setattr(self, "_auto_query_running", True), self._auto_query_loop()])
    def _quiesce_for(self, ms: int) -> None:
        # block auto-query until now + ms
        t = time.monotonic() + (ms / 1000.0)
        self._busy_until = max(self._busy_until, t)

    def _device_key_for(self, name: str) -> str:
        return {"fan": "COOL", "lamp": "LAMP", "shutter": "SHUTTER"}[name]

    def _await_status(self, key: str, target: int, timeout_s: float = 1.5, poll_s: float = 0.12) -> bool:
        # poll FS until key == target or timeout
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            data = self.psu.query_status()
            val = int(data.get(key, -1)) if data else -1
            if val == target:
                # reflect to switches once confirmed
                self._apply_status_to_switches(data)
                return True
            time.sleep(poll_s)
        return False


    def log(self, text: str) -> None:
        """
        append text to the output box.
        """

        timestamp = datetime.now().strftime("[%Y-%m-%d %H:%M:%S] ")
        message = timestamp + text
        self.output.insert("end", text + "\n")
        self.output.see("end")

        # get the path of the directory where the script is located
        log_path = os.path.join(os.path.dirname(__file__), "log.txt")

        # append the same text to a file
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(message + "\n")

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
        target = self.serial_var.get() # self.serial_var.get().strip()
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
    
    def handle_switch(self, name: str, var: tk.BooleanVar) -> None:
        if getattr(self, "_syncing_from_status", False):
            return

        if not self.ensure_connected():
            var.set(not var.get())
            return

        desired = var.get()

        try:
            cmd = command_for(name, desired)
            self._quiesce_for(1500)
            self.psu.send_command(cmd, wait_s=0.12, post_quiet_s=0.5)
            self.log(f"> {cmd}")
            # confirm via FS once before auto-query resumes normal cadence
            key = self._device_key_for(name)
            target = 1 if desired else 0

            # while we are confirming, prevent UI flips from stale reads
            self._syncing_from_status = True
            ok = self._await_status(key, target, timeout_s=1.5, poll_s=0.12)
            if not ok:
                # revert local UI if device didn’t take the command
                var.set(not desired)
                self.log(f"[warn] {key} did not reach {target} within timeout")

            
        except Exception as e:
            # on any exception, revert and show a *real* error dialog
            try:
                var.set(not desired)
            except Exception:
                pass
            self.log(f"[error] {e}")
            messagebox.showerror("command failed", str(e))
            return
        
        finally:
            self._syncing_from_status = False


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
            
        def as_float(val, default=0.0):
            try:
                return float(val)
            except (TypeError, ValueError):
                return default

        # start guarded section: flips won't trigger handle_switch
        self._syncing_from_status = True
        try:
            if "COOL" in status:
                self.fan_var.set(as_bool(status["COOL"]))
            if "LAMP" in status:
                self.lamp_var.set(as_bool(status["LAMP"]))
            if "SHUTTER" in status:
                self.shutter_var.set(as_bool(status["SHUTTER"]))
            
            # --- live numeric readouts ---
            if "VOLTAGE" in status:
                voltage = as_float(status["VOLTAGE"])/config["LampVoltageFactor"]
                self.voltage_var.set(f"{voltage:.2f} V")

            if "CURRENT" in status:
                current = as_float(status["CURRENT"])/config["LampCurrentFactor"]
                self.current_var.set(f"{current:.3f} A")

            if "POWER" in status:
                power_raw = as_float(status["POWER"])/config["LampPowerFactor"]
                self.power_var.set(f"{power_raw:.1f} W")

            if "HOUR" and "MINUTES" in status:
                lamplife = status["HOUR"] * 60 + status["MINUTES"]
                self.lamplife_var.set(f"{lamplife} min")

        finally:
            self._syncing_from_status = False


    def set_power(self) -> None:
        """
        parse the entry, clamp if needed, and call the communicator helper.
        """
        if not self.ensure_connected():
            return
        try:
            # reads decimal value
            user_value = float(self.power_vardigit.get())
            user_value = max(config["MinimumOutput"], min(user_value, config["MaximumOutput"]))

            scaled_value = int(user_value * 10)  
        except ValueError:
            messagebox.showwarning("Invalid power", "Enter a number between 70.0 and 105.0")
            return

        # limits
        # scaled_value = max(config["MinimumOutput"], min(scaled_value, config["MaximumOutput"]))

        try:
            resp = self.psu.set_power(scaled_value)
            self.log(f"> P={scaled_value:04d}\n< {resp}")
        except Exception as e:
            messagebox.showerror("Set power failed", str(e))

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

    def _on_power_edit_start(self, event=None):
        """User started editing power manually."""
        self._editing_power = True

    def _on_power_edit_end(self, event=None):
        """User left the power field (focus lost)."""
        self._editing_power = False

    def _on_power_commit(self, event=None):
        """User pressed Enter — commit edit and set power."""
        self._editing_power = False
        self.focus()  # remove focus from entry
        self.set_power()  # same as clicking the button