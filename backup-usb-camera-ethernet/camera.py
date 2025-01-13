# import cv2
# import socket
# import time

# # Konfigurasjon
# IP = "192.168.137.100" # PCens IP (topside)
# PORT = 1234
# FRAME_WIDTH = 1920  # Endres til 1920x1080 for bruk  # Alt: 640x480
# FRAME_HEIGHT = 1080
# FPS = 30  # Endres til 30 FPS for bruk  # Alt: 15 fps
# MAX_PACKET_SIZE = 65000  # Maks UDP-pakkestørrelse
# INDEX = 0 # Kamera indeks hos enheten som leser kamera

# def main():
#     # Åpne kamera
#     cap = cv2.VideoCapture(INDEX)
#     cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
#     cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)
#     cap.set(cv2.CAP_PROP_FPS, FPS)
#     cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))

#     if not cap.isOpened():
#         print("Kunne ikke åpne kamera.")
#         return

#     # Opprett UDP-socket
#     sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
#     print(f"Starter sending til {IP}:{PORT}...")

#     while True:
#         ret, frame = cap.read()
#         if not ret:
#             print("Feil ved lesing fra kamera.")
#             break

#         # Komprimer rammen til JPEG
#         _, buffer = cv2.imencode('.jpg', frame)
#         data = buffer.tobytes()

#         # Splitter data i mindre pakker
#         total_packets = len(data) // MAX_PACKET_SIZE + 1
#         for i in range(total_packets):
#             start = i * MAX_PACKET_SIZE
#             end = start + MAX_PACKET_SIZE
#             packet = data[start:end]


#             # Legger til header med pakkeindeks
#             header = f"{i}/{total_packets}|".encode('utf-8')  # Separator for tydelig header
#             sock.sendto(header + packet, (IP, PORT))
#             print(f"Sendt pakke {i+1}/{total_packets}")  # Feilsøking

#         time.sleep(1 / FPS)  # For å holde FPS stabil

#     cap.release()
#     sock.close()

# if __name__ == "__main__":
#     main()


import cv2
import socket
import time
import subprocess
import sys

# Konfigurasjon
IP = "192.168.137.100"  # PCens IP (topside)
PORT = 1234
FRAME_WIDTH = 1920  # Alternativ: 640x480
FRAME_HEIGHT = 1080
FPS = 30  # Alternativ: 15
MAX_PACKET_SIZE = 65000  # Maks UDP-pakkestørrelse
INDEX = 0  # Kameraindeks på enheten
ETH_INTERFACE = "eth0"  # Ethernet-grensesnitt

def is_ethernet_connected():
    """Sjekker om Ethernet er koblet til ved hjelp av ethtool."""
    try:
        result = subprocess.run(
            ["ethtool", ETH_INTERFACE],
            capture_output=True,
            text=True,
            check=True
        )
        return "Link detected: yes" in result.stdout
    except subprocess.CalledProcessError:
        return False

def main():
    # Sjekk Ethernet-status ved start
    if not is_ethernet_connected():
        print("Ingen Ethernet-forbindelse. Avslutter.")
        sys.exit(1)

    # Åpne kamera
    cap = cv2.VideoCapture(INDEX)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)
    cap.set(cv2.CAP_PROP_FPS, FPS)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))

    if not cap.isOpened():
        print("Kunne ikke åpne kamera.")
        return

    # Opprett UDP-socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    print(f"Starter sending til {IP}:{PORT}...")

    last_check_time = time.time()

    while True:
        # Sjekk Ethernet-status hvert 5. sekund
        if time.time() - last_check_time > 5:
            if not is_ethernet_connected():
                print("Ethernet-forbindelse mistet. Avslutter.")
                break
            last_check_time = time.time()

        # Les rammen fra kameraet
        ret, frame = cap.read()
        if not ret:
            print("Feil ved lesing fra kamera.")
            break

        # Komprimer rammen til JPEG
        _, buffer = cv2.imencode('.jpg', frame)
        data = buffer.tobytes()

        # Splitter data i mindre pakker
        total_packets = len(data) // MAX_PACKET_SIZE + 1
        for i in range(total_packets):
            start = i * MAX_PACKET_SIZE
            end = start + MAX_PACKET_SIZE
            packet = data[start:end]

            # Legger til header med pakkeindeks
            header = f"{i}/{total_packets}|".encode('utf-8')  # Separator for tydelig header
            sock.sendto(header + packet, (IP, PORT))
            print(f"Sendt pakke {i+1}/{total_packets}")  # Feilsøking

        time.sleep(1 / FPS)  # For å holde FPS stabil

    # Rydd opp ressurser ved avslutning
    cap.release()
    sock.close()
    print("Avsluttet riktig.")

if __name__ == "__main__":
    main()

