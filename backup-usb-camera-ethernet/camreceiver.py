import cv2
import socket
import numpy as np
import time
import sys

# Konfigurasjon
PC_IP = "192.168.137.100"  # PCens IP (topside)
PORT = 1234
BUFFER_SIZE = 65536

def print_spinner(message, delay=0.2):
    """Viser en enkel spinner etter en melding."""
    spinner = ['-', '\\', '|', '/']  # Grafikken til spinneren
    for frame in spinner:
        sys.stdout.write(f"\r{message} {frame}")
        sys.stdout.flush()
        time.sleep(delay)

def main():
    # Opprett UDP-socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((PC_IP, PORT))
    sock.settimeout(3)  # Timeout etter 5 sekunder
    print(f"Lytter på {PC_IP}:{PORT} etter videostrøm...")

    buffer = {}
    total_packets = 1
    video_streaming = False  # Kontroll for om video strøm er opprettet
    last_status = ""  # Holder forrige status for å unngå repetitiv utskrift

    while True:
        try:
            # Mottar data fra sender
            packet, addr = sock.recvfrom(BUFFER_SIZE)

            # Skiller ut header og data
            if b"|" not in packet:
                new_status = "Ugyldig pakkeformat mottatt."
                if new_status != last_status:
                    print(f"\r{new_status}")
                    last_status = new_status
                continue
            
            header, data = packet.split(b"|", 1)
            
            # Hent pakkeinformasjon
            index, total = map(int, header.decode('utf-8').split('/'))
            total_packets = total
            buffer[index] = data

            # Når alle pakkene er mottatt, dekode rammen
            if len(buffer) == total_packets:
                if not video_streaming:
                    print("\nVideostrøm opprettet - viser bilder...")
                    video_streaming = True
                    last_status = "streaming"

                frame_data = b''.join([buffer[i] for i in range(total_packets)])
                frame = cv2.imdecode(np.frombuffer(frame_data, dtype=np.uint8), cv2.IMREAD_COLOR)
                
                if frame is not None:
                    cv2.imshow("Videostrøm fra RPi (MJPG)", frame)
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        break
                
                # Tøm bufferet for neste ramme
                buffer.clear()

        except socket.timeout:
            # Dynamisk ventegrafikk
            new_status = "Ingen data mottatt - venter på sender..."
            if new_status != last_status:
                print(f"\r{new_status}")
                last_status = new_status
            print_spinner(new_status)

            # Hvis strømmen var aktiv, meld at den er mistet
            if video_streaming:
                print("\nMistet videostrøm, prøver igjen...")
                video_streaming = False

        except Exception as e:
            new_status = f"Feil under mottak: {e}"
            if new_status != last_status:
                print(f"\r{new_status}")
                last_status = new_status
            break

    sock.close()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
