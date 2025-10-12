import socket
import json

# Funksjon for å koble til TCP-serveren og motta data
def receive_data(host, port):
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client_socket.connect((host, port))
    print(f"Koblet til server på {host}:{port}")

    try:
        while True:
            data = client_socket.recv(4096).decode("utf-8")  # Mottar data fra server
            if not data:
                break  # Avslutt hvis tilkoblingen er lukket
            try:
                json_data = json.loads(data)  # Parse JSON-data
                print(json.dumps(json_data, indent=4))  # Vis data på en lesbar måte
            except json.JSONDecodeError:
                print("Feil: Mottok ugyldig JSON-data.")
    except KeyboardInterrupt:
        print("\nAvslutter klienten...")
    finally:
        client_socket.close()

if __name__ == "__main__":
    # IP og port for serveren
    HOST = "192.168.100.20"  # Endres til RPi-ens IP-adresse
    PORT = 65432             # Må matche porten brukt av serveren

    receive_data(HOST, PORT)
