# Topside Setup Guide

## Download

Get the latest release from the [Releases page](../../releases).

| Platform | File | Notes |
|----------|------|-------|
| Windows (recommended) | `Topside-vX.Y.Z-setup.exe` | Standard installer with Start Menu shortcut |
| Windows (portable)    | `Topside-vX.Y.Z-windows.zip` | Extract anywhere and run `Topside.exe` |
| Linux                 | `Topside-vX.Y.Z-linux.zip` | `chmod +x Topside && ./Topside` |
| macOS                 | `Topside-vX.Y.Z-macos.zip` | See SmartScreen note below |

## First Launch (Windows)

1. Run the installer.
2. Windows SmartScreen will likely show **"Windows protected your PC"**. Click **More info → Run anyway**. The installer is not code-signed; this is expected.
3. After install, launch **Topside** from the Start Menu.
4. A console window appears and the dashboard server starts on port 5000.
5. Open a web browser and go to <http://localhost:5000>.

To stop the app, close the console window.

## Network Setup

The Topside PC must be on the **same subnet as the onboard device**, otherwise no telemetry, video, or control will work.

### Expected addresses

| Role            | Address              |
|-----------------|----------------------|
| Onboard device  | `192.168.1.100`      |
| IP camera       | `192.168.1.168`      |
| Topside PC      | any unused address in `192.168.1.0/24`, e.g. `192.168.1.10` |

### Setting a static IP on Windows

1. Open **Settings → Network & internet**.
2. Click the active adapter (the one connected to the device, usually **Ethernet**).
3. Next to **IP assignment**, click **Edit** → choose **Manual** → toggle **IPv4** on.
4. Enter:
   - **IP address:** `192.168.1.10`
   - **Subnet mask:** `255.255.255.0`
   - **Gateway:** leave blank
   - **DNS:** leave blank
5. Save.

To verify, open a Command Prompt and run `ping 192.168.1.100`. You should see replies.

### Ports used

| Port       | Direction | Purpose                       |
|------------|-----------|-------------------------------|
| `5000/tcp` | local     | Dashboard (browser → app)     |
| `12345/udp`| outbound  | Control commands → device     |
| `5002/udp` | inbound   | IMU telemetry                 |
| `12346/udp`| inbound   | Resource monitor              |
| `6969/udp` | inbound   | RPi camera stream             |

If you have a firewall (Windows Defender or similar), allow inbound UDP on `5002`, `12346`, and `6969`.

## Troubleshooting

- **No video / no telemetry** — verify the static IP, then `ping 192.168.1.100`. If the ping fails, the network is the problem, not the app.
- **Settings don't persist between launches** — the config lives at `%LOCALAPPDATA%\Topside\data\config.json`. The installer only writes a starter file if it doesn't exist, so reinstalling won't wipe your settings.
- **App window closes immediately** — launch from the Start Menu (not by double-clicking inside Program Files). If the console flashes and disappears, run `Topside.exe` from `cmd.exe` to see the error.
