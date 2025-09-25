import tkinter as tk
from tkinter import scrolledtext, messagebox
from src.serial_comm import PowerSupplyCommunicator

class PowerSupplyGUI(tk.Tk):
    def __init__(self, port, baud_rate=9600):
        super().__init__()
        self.title("Power Supply Controller")
        self.geometry("400x300")

        self.psu = PowerSupplyCommunicator(port, baud_rate)
        try:
            self.psu.connect()
        except Exception as e:
            messagebox.showerror("connection error", f"could not connect: {e}")
            self.destroy()
            return

        # create buttons for commands
        commands = {
            "FSXXX\n": "get status",
            "C1\n": "fan on",
            "C0\n": "fan off",
            "S1\n": "shutter on",
            "S0\n": "shutter off",
            "L1\n": "lamp on",
            "L0\n": "lamp off"

        }

        btn_frame = tk.Frame(self)
        btn_frame.pack(pady=10)

        for cmd, label in commands.items():
            btn = tk.Button(btn_frame, text=label, width=12,
                            command=lambda c=cmd: self.send_command(c))
            btn.pack(side=tk.LEFT, padx=5)

        # scrolled text for output
        self.output_area = scrolledtext.ScrolledText(self, width=50, height=10)
        self.output_area.pack(padx=10, pady=10)

        # close connection on exit
        self.protocol("wm_delete_window", self.on_close)
      
    
    def send_command(self, command):
        try:
            response = self.psu.send_command(command + "\r")
            # print(f"RAW RESPONSE: {repr(response)}")
            print("-------- raw response --------")
            print(repr(response))
            print("------------------------------")


            self.output_area.insert(tk.END, f"> {command}\n{response}\n\n")
            self.output_area.see(tk.END)
        except Exception as e:
            messagebox.showerror("error", f"failed to send command: {e}")

    def set_power(self):
        value = self.power_entry.get().strip()

        if not value.isdigit():
            messagebox.showwarning("invalid input", "please enter a number.")
            return

        power = int(value)
        if not (0 <= power <= 9999):
            messagebox.showwarning("invalid range", "value must be 0–9999.")
            return

        # pad the number with leading zeros to 4 digits
        formatted_value = f"{power:04d}"
        command = f"P={formatted_value}"

        self.send_command(command)


    def on_close(self):
        self.psu.disconnect()
        self.destroy()

if __name__ == "__main__":
    port = "COM3"  # adjust to your port
    app = PowerSupplyGUI(port)
    app.mainloop()
