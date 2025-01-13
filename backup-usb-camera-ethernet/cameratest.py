import cv2

def list_camera_details(index):
    """
    Viser detaljer om kameraet for en gitt indeks.
    """
    cap = cv2.VideoCapture(index)
    if not cap.isOpened():
        print(f"Kamera {index} er ikke tilgjengelig.")
        return False

    print(f"\nDetaljer for kamera med indeks {index}:")

    # Hent nåværende oppløsning
    width = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
    height = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
    print(f"  - Nåværende oppløsning: {int(width)}x{int(height)}")

    # Hent støttet FPS
    fps = cap.get(cv2.CAP_PROP_FPS)
    print(f"  - Nåværende FPS: {fps}")

    # Sjekk komprimeringstype
    fourcc = int(cap.get(cv2.CAP_PROP_FOURCC))
    codec = "".join([chr((fourcc >> 8 * i) & 0xFF) for i in range(4)])
    print(f"  - Komprimeringstype: {codec} (FourCC)")

    # Forsøk å sette til MJPEG og sjekk om det støttes
    if cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG')):
        print("  - MJPEG støttes!")
    else:
        print("  - MJPEG støttes ikke.")

    cap.release()
    return True


def main():
    print("Sjekker tilkoblede kameraer...")

    max_indices_to_check = 5  # Antall kameraindekser å sjekke
    camera_found = False

    for i in range(max_indices_to_check):
        print(f"\nTester kameraindeks {i}...")
        if list_camera_details(i):
            camera_found = True

    if not camera_found:
        print("\nIngen kameraer oppdaget. Kontroller tilkoblinger.")

if __name__ == "__main__":
    main()
