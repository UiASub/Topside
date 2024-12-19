import socket
import json

# Definer Topside (Host) serverens IP-adresse og port
HOST = '192.168.137.100'  # Sett PC til static IP server. Ethernet->IPv4 address: 192.168.137.100. Netmask/IPv4 mask: 255.255.255.0. (Default) gateway: 'blank'.
PORT = 1234  # Velg samme port for Topside- og ROV-program. #Port 1234 (123x)

# Opprett en socket-objekt
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
    server_socket.bind((HOST, PORT))  # Bind til valgt adresse og port
    server_socket.listen()  # Lytt etter innkommende tilkoblinger
    print(f"Serveren lytter på {HOST}:{PORT}...")

    # Vente på en klient-tilkobling
    conn, addr = server_socket.accept()
    with conn:
        print(f"Tilkobling mottatt fra {addr}")

        while True:
            data = conn.recv(1024)  # Motta data fra klienten (maks 1024 bytes)
            if not data:
                break  # Avslutt hvis klienten kobler fra

            # Dekode og last inn mottatt JSON-data
            try:
                received_json = data.decode()
                new_data = json.loads(received_json)
                print(f"Mottatt JSON-data: {new_data}")

                # Last inn eksisterende data fra data.json
                try:
                    with open('data.json', 'r') as json_file:
                        current_data = json.load(json_file)
                except (FileNotFoundError, json.JSONDecodeError):
                    current_data = {}  # Hvis filen ikke finnes eller er korrupt, start med tom data

                # Oppdater den eksisterende dataen med den nye informasjonen
                current_data.update(new_data)

                # Skriv oppdatert data tilbake til data.json
                with open('data.json', 'w') as json_file:
                    json.dump(current_data, json_file, indent=4)

                print("data.json er oppdatert med ny informasjon.")

            except json.JSONDecodeError:
                print("Feil: Mottatt data er ikke gyldig JSON.")

            # Send en bekreftelse tilbake til klienten
            conn.sendall(b"Data mottatt og lagret")
