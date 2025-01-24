import json
import random
import os
import time
import socket
from threading import Thread

# Sett filsti til data.json i hovedmappen
FILE_NAME = os.path.join(os.getcwd(), "data.json")

# Funksjon for å generere mock-data
def generate_mock_data():
    data = {
        "thrusters": {
            f"{position}": {
                "power": random.randint(400, 550),
                "temp": random.randint(20, 30)
            }
            for position in [
                "U_FWD_P", "U_FWD_S", "U_AFT_P", "U_AFT_S",
                "L_FWD_P", "L_FWD_S", "L_AFT_P", "L_AFT_S"
            ]
        },
        "9dof": {
            "acceleration": {
                "x": round(random.uniform(-1, 1), 2),
                "y": round(random.uniform(-1, 1), 2),
                "z": round(random.uniform(9.5, 10), 2)
            },
            "gyroscope": {
                "x": round(random.uniform(-0.1, 0.1), 2),
                "y": round(random.uniform(-0.1, 0.1), 2),
                "z": round(random.uniform(-0.1, 0.1), 2)
            },
            "magnetometer": {
                "x": round(random.uniform(30, 50), 2),
                "y": round(random.uniform(-30, 30), 2),
                "z": round(random.uniform(10, 20), 2)
            },
        },
        "lights": {
            f"Light{i}": random.randint(0, 100)
            for i in range(1, 5)
        },
        "battery": random.randint(80, 100),
        "depth": {
            "dpt": random.randint(100, 200),
            "dptSet": random.randint(100, 200)
        }
    }
    return data

# Funksjon for å oppdatere data.json
def update_json():
    data = generate_mock_data()
    with open(FILE_NAME, "w") as file:
        json.dump(data, file, indent=4)

# Kontinuerlig oppdatering av JSON-filen
def update_json_file(update_interval_ms):
    while True:
        update_json()
        time.sleep(update_interval_ms / 1000)

# TCP-server for å sende JSON-data
def tcp_server(host, port):
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.bind((host, port))
    server_socket.listen(1)
    print(f"Server lytter på {host}:{port}...")

    while True:
        client_socket, client_address = server_socket.accept()
        print(f"Tilkobling fra {client_address}")

        try:
            while True:
                with open(FILE_NAME, "r") as file:
                    data = file.read()
                client_socket.sendall(data.encode("utf-8"))
                time.sleep(1)  # Send hvert sekund (kan justeres)
        except (ConnectionResetError, BrokenPipeError):
            print("Klient koblet fra.")
        finally:
            client_socket.close()

if __name__ == "__main__":
    # Oppdater JSON-fila i en egen tråd
    update_interval_ms = 500  # Frekvens: 500 ms (kan justeres)
    Thread(target=update_json_file, args=(update_interval_ms,), daemon=True).start()

    # Start TCP-serveren
    HOST = "192.168.100.20"  # IP-adresse til RPi
    PORT = 65432            # Valgfri port
    tcp_server(HOST, PORT)
