# src/cgui.py
import customtkinter as ctk
from tkinter import messagebox
from src.serial_comm import PowerSupplyCommunicator, find_com_port_by_sf_response
from serial.tools import list_ports


ctk.set_appearance_mode("System")  # options: "system", "dark", "light"
ctk.set_default_color_theme("blue")  # you can change this to "green", "dark-blue", etc.



class PowerSupplyGUI(ctk.CTk):
    def __init__(self, port, baud_rate=9600):
        super().__init__()
        self.title("Power Supply Controller")
        self.geometry("500x800")

        # theme toggle dropdown
        theme_frame = ctk.CTkFrame(self)
        theme_frame.pack(pady=10)

        ctk.CTkLabel(theme_frame, text="Theme:").pack(side="left", padx=5)

        self.theme_option = ctk.CTkOptionMenu(theme_frame,
                                              values=["System", "Light", "Dark"],
                                              command=self.change_theme)
        self.theme_option.set("System")
        self.theme_option.pack(side="left", padx=5)


        # Serial port selector
        self.psu = None
        self.baud_rate = baud_rate

        port_frame = ctk.CTkFrame(self)
        port_frame.pack(pady=10)

        ctk.CTkLabel(port_frame, text="Select Serial Port:").pack(side="left", padx=5)

        available_ports = [port.device for port in list_ports.comports()]
        self.port_option = ctk.CTkOptionMenu(port_frame, values=available_ports)
        if available_ports:
            self.port_option.set(available_ports[0])
        self.port_option.pack(side="left", padx=5)

        connect_btn = ctk.CTkButton(port_frame, text="Connect", command=self.connect_to_port)
        connect_btn.pack(side="left", padx=5)

        



        # command buttons
        commands = {
            "FS\n": "Get Status",
            "C1\n": "Fan On",
            "C0\n": "Fan Off",
            "S1\n": "Shutter On",
            "S0\n": "Shutter Off",
            "L1\n": "Lamp On",
            "L0\n": "Lamp Off"
        }

        btn_frame = ctk.CTkFrame(self)
        btn_frame.pack(side="top", padx=5, pady=10)

        for cmd, label in commands.items():
            btn = ctk.CTkButton(btn_frame, text=label, width=100,
                                command=lambda c=cmd: self.send_command(c))
            # btn.pack(side="left", padx=5)
            btn.pack(pady=5)

        # output area
        self.output_area = ctk.CTkTextbox(self, width=450, height=50)
        self.output_area.pack(padx=10, pady=10)

        # power entry and set button
        entry_frame = ctk.CTkFrame(self)
        entry_frame.pack(pady=10)

        self.power_entry = ctk.CTkEntry(entry_frame, placeholder_text="Enter power (0–9999)", width=150)
        self.power_entry.pack(side="left", padx=5)

        set_btn = ctk.CTkButton(entry_frame, text="Set Power", command=self.set_power)
        set_btn.pack(side="left", padx=5)

        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def change_theme(self, mode):
        ctk.set_appearance_mode(mode)

    def connect_to_port(self):
        TARGET_SERIAL = "1234"
        matched_port = find_com_port_by_sf_response(TARGET_SERIAL, self.baud_rate)
        # matched_port = self.port_option.get()
        if not matched_port:
            messagebox.showwarning("No Port", "SN not found")
            return

        self.psu = PowerSupplyCommunicator(matched_port, self.baud_rate)
        try:
            self.psu.connect()
            response = self.psu.send_command("FS\n")  # Or another safe 'status' command
            if not response.strip():
                raise Exception("No response from device. Is it powered on?")
            messagebox.showinfo("Connected", f"Connected to {matched_port}")
            print("Device response:", response)            
        except Exception as e:
            self.psu.disconnect()
            self.psu = None
            messagebox.showerror("Connection Error", f"Could not connect: {e}")

    def send_command(self, command):
        if not self.psu:
            messagebox.showerror("Not Connected", "Please connect to a serial port first.")
            return
        try:
            response = self.psu.send_command(command + "\r")
            cleaned_response = response.replace('\x00', '').strip()

            print("RAW BYTES:", repr(cleaned_response))

            self.output_area.insert("end", f"> {command}\n{response}\n\n")
            self.output_area.see("end")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to send command: {e}")

    def set_power(self):
        value = self.power_entry.get().strip()

        if not self.psu:
            messagebox.showerror("Not Connected", "Please connect to a serial port first.")
            return

        if not value.isdigit():
            messagebox.showwarning("Invalid Input", "Please enter a number.")
            return

        power = int(value)
        if not (0 <= power <= 9999):
            messagebox.showwarning("Invalid Range", "Value must be between 0 and 9999.")
            return

        formatted_value = f"{power:04d}"
        command = f"P={formatted_value}"
        self.send_command(command)

    def on_close(self):
        if self.psu:
            self.psu.disconnect()
        self.destroy()

if __name__ == "__main__":
    port = "COM3"  # adjust to your port
    app = PowerSupplyGUI(port)
    app.mainloop()
