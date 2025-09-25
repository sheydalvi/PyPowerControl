from src.gui import PowerSupplyGUI

if __name__ == "__main__":
    port = "COM3"  # change to your port
    app = PowerSupplyGUI(port)
    app.mainloop()
