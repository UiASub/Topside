import socket
import subprocess
import time
import sys

# Konfigurasjon
PC_IP = "192.168.137.100"  # PCens IP (topside)
PORT = 1234
BUFFER_SIZE = 65536

def print_spinner(message, delay=0.2):
    """Viser en enkel spinner etter en melding."""
    spinner = ['-', '\\', '|', '/']
    while True:
        for frame in spinner:
            sys.stdout.write(f"\r{message} {frame}")
            sys.stdout.flush()
            time.sleep(delay)
            yield  # Tillater avbrytelse ved statusendring

def main():
    # Opprett UDP-socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((PC_IP, PORT))
    print(f"Lytter på {PC_IP}:{PORT} etter videostrøm...")

    buffer = {}
    total_packets = 1
    ffmpeg_process = None
    video_streaming = False  # Kontroll for aktiv strøm
    last_status = ""
    spinner = None

    while True:
        try:
            if spinner:
                next(spinner)  # Fortsett spinner hvis aktiv

            # Mottar data fra sender
            packet, addr = sock.recvfrom(BUFFER_SIZE)

            # Skiller ut header og data
            if b"|" not in packet:
                new_status = "Ugyldig pakkeformat mottatt."
                if new_status != last_status:
                    print(f"\r{new_status}")
                    last_status = new_status
                    spinner = print_spinner("Venter på gyldige pakker")  # Start spinner
                continue

            header, data = packet.split(b"|", 1)
            index, total = map(int, header.decode('utf-8').split('/'))
            total_packets = total
            buffer[index] = data

            # Når alle pakkene er mottatt, dekode rammen
            if len(buffer) == total_packets:
                if spinner:
                    spinner = None  # Stopp spinner

                frame_data = b''.join([buffer[i] for i in range(total_packets)])
                buffer.clear()

                # Start FFmpeg hvis det ikke er startet
                if ffmpeg_process is None:
                    spinner = print_spinner("Starter videostrøm med FFmpeg")  # Start spinner
                    ffmpeg_process = subprocess.Popen(
                        [
                            'ffplay',
                            '-fflags', 'nobuffer',        # Lav latens, ingen buffer
                            '-flags', 'low_delay',        # Aktiver lav-latency-modus
                            '-f', 'mjpeg',                # Input-format
                            '-i', '-',                   # Les fra stdin
                            '-an',                       # Deaktiver lyd
                            '-framedrop',                # Dropp rammer hvis treghet oppstår
                            '-window_title', 'RPi Video'
                        ],
                        stdin=subprocess.PIPE,
                        stderr=subprocess.DEVNULL,       # Skjul FFmpeg-logg
                        stdout=subprocess.DEVNULL        # Skjul FFmpeg-logg
                    )

                ffmpeg_process.stdin.write(frame_data)

                if not video_streaming:
                    print("\nVideostrøm opprettet - viser bilder...")
                    video_streaming = True
                    last_status = "streaming"

        except socket.timeout:
            new_status = "Ingen data mottatt - venter på sender..."
            if new_status != last_status:
                print(f"\r{new_status}")
                last_status = new_status
                spinner = print_spinner(new_status)  # Start spinner

            if video_streaming:
                print("\nMistet videostrøm, prøver igjen...")
                video_streaming = False

        except Exception as e:
            new_status = f"Feil under mottak: {e}"
            if new_status != last_status:
                print(f"\r{new_status}")
                last_status = new_status
                spinner = None  # Stopp spinner ved kritisk feil
            break

    if ffmpeg_process:
        ffmpeg_process.terminate()
    sock.close()

if __name__ == "__main__":
    main()
