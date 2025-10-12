import serial
import json


# port is typically "COM3" or some other "COMx" port.
def read_joy(port: str) -> None:
    """Oppretter kobling til joystick over Seriel med port __port__ og leser data fra den.
    Kjører kontinuerlig i en loop og skriver data til filen data/data.json.

    Bruk: spawn denne ut i en egen prosess med multiprosessing librariet.

    Args:
        port (str): Dette er serial porten som joystick er koblet til. F.eks. "COM3" eller "/dev/ttyUSB0"
    """

    try:
        ser = serial.Serial(port, 115200, timeout=1)
    except serial.SerialException as e:
        print(f"Joystick: Failed to open serial port {port}: {e}")
        return

    while True:
        try:
            # Read a line from Serial
            line = ser.readline().decode("utf-8").strip()

            if line:
                # Parse JSON
                data = json.loads(line)

                # Open the file safely
                with open("data/data.json", "r+") as file:
                    try:
                        existing_data = json.load(file)
                    except json.JSONDecodeError:
                        existing_data = (
                            {}
                        )  # Default empty dictionary if file is invalid

                    existing_data["Thrust"] = data["Thrust"]
                    existing_data["Gain"] = data["Gain"]

                    # Go to the beginning of the file before writing
                    file.seek(0)
                    json.dump(existing_data, file, indent=4)
                    file.truncate()  # Remove leftover content from previous writes

        except json.JSONDecodeError:
            print("Invalid JSON received:", line)

        except KeyboardInterrupt:
            print("\nExiting...")
            break

    ser.close()
