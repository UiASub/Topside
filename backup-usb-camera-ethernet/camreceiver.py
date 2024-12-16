import cv2
import socket
import numpy as np

# Konfigurasjon
PC_IP = "192.168.137.100"  # PCens IP (topside)  # Kan teste med webcam og "localhost". Husk å kjør maksimalt ett script i VScode
PORT = 1234
BUFFER_SIZE = 65536

def main():
    # Opprett UDP-socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((PC_IP, PORT))
    sock.settimeout(5)  # Timeout etter 5 sekunder
    print(f"Lytter på {PC_IP}:{PORT} etter videostrøm...")

    buffer = {}
    total_packets = 1

    while True:
        try:
            # Mottar data fra sender
            packet, addr = sock.recvfrom(BUFFER_SIZE)

            # Skiller ut header og data
            if b"|" not in packet:
                print("Ugyldig pakkeformat mottatt.")
                continue
            
            header, data = packet.split(b"|", 1)
            
            # Hent pakkeinformasjon
            index, total = map(int, header.decode('utf-8').split('/'))
            total_packets = total
            buffer[index] = data

            # Når alle pakkene er mottatt, dekode rammen
            if len(buffer) == total_packets:
                print(f"Alle {total_packets} pakker mottatt, dekoder ramme...")
                frame_data = b''.join([buffer[i] for i in range(total_packets)])
                frame = cv2.imdecode(np.frombuffer(frame_data, dtype=np.uint8), cv2.IMREAD_COLOR)
                
                if frame is not None:
                    cv2.imshow("Videostrøm fra RPi (MJPG)", frame)
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        break
                
                # Tøm bufferet for neste ramme
                buffer.clear()
        except socket.timeout:
            print("Ingen data mottatt - venter på sender...")
        except Exception as e:
            print(f"Feil under mottak: {e}")
            break

    sock.close()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()

