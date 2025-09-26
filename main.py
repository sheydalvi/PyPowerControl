# main.py
from src.cgui import PowerSupplyGUI

# TARGET_SERIAL = "1234"

if __name__ == "__main__":
    port = "COM3"  # change to your port
    app = PowerSupplyGUI(port)
    # app = PowerSupplyGUI(port=None)
    app.mainloop()
