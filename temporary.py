import socket
import struct


#temporary UDP server to visualize Bitmask packets for testing locally
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind(("0.0.0.0", 12345))
print("Listening on port 12345...")

while True:
    data, addr = sock.recvfrom(1024)
    if len(data) == 16:  # 4 (seq) + 8 (payload) + 4 (crc)
        seq, payload, crc = struct.unpack("!IQI", data)
        # Decode payload
        surge = ((payload >> 0) & 0xFF) - 128
        sway = ((payload >> 8) & 0xFF) - 128
        heave = ((payload >> 16) & 0xFF) - 128
        roll = ((payload >> 24) & 0xFF) - 128
        pitch = ((payload >> 32) & 0xFF) - 128
        yaw = ((payload >> 40) & 0xFF) - 128
        light = (payload >> 48) & 0xFF
        manip = ((payload >> 56) & 0xFF) - 128
        print(f"seq={seq:5d} surge={surge:+4d} sway={sway:+4d} heave={heave:+4d} "
              f"yaw={yaw:+4d} pitch={pitch:+4d} roll={roll:+4d} light={light:3d} manip={manip:3d}")