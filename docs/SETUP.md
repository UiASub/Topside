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
3. On the installer task page, select **Configure MCU Ethernet adapter to 10.77.0.1/24** if this PC is connected directly to the MCU network. Windows will ask for administrator approval for this step.
4. After install, launch **Topside** from the Start Menu.
5. A console window appears and the dashboard server starts on port 5000.
6. Open a web browser and go to <http://localhost:5000>.

To stop the app, close the console window.

## Network Setup

The Topside PC must be on the **same subnet as the onboard device**, otherwise no telemetry, video, or control will work.

### Expected addresses

| Role            | Address              |
|-----------------|----------------------|
| Onboard device  | `10.77.0.2`          |
| IP camera       | `192.168.1.168`      |
| Topside PC      | `10.77.0.1/24` on the MCU Ethernet adapter |

### Automated MCU Ethernet setup

Topside includes helper scripts that configure the selected Ethernet adapter as `10.77.0.1/24`, then try to ping the MCU at `10.77.0.2`. If the ping fails, the scripts warn and continue so setup can still finish before the cable or MCU is connected.

On Fedora/Linux with NetworkManager:

```bash
./tools/k2-ethernet.sh up
```

On Windows, run from an Administrator PowerShell:

```powershell
.\tools\k2-ethernet.ps1 up
```

Both scripts show a menu of Ethernet adapters and mark the most likely USB Ethernet adapter as recommended. Use `status` to inspect the current setup and `down` to remove the direct-link configuration:

```bash
./tools/k2-ethernet.sh status
./tools/k2-ethernet.sh down
```

```powershell
.\tools\k2-ethernet.ps1 status
.\tools\k2-ethernet.ps1 down
```

### Manual static IP on Windows

The Windows installer can do this automatically if you select **Configure MCU Ethernet adapter to 10.77.0.1/24** during install. The portable Windows zip also includes the same helper script:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\configure_ethernet.ps1
```

Run the command from an Administrator PowerShell. By default it targets an adapter named `Ethernet`; if that does not exist, it uses the only active wired adapter. To choose a specific adapter:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\configure_ethernet.ps1 -InterfaceAlias "Ethernet 2"
```

Manual setup:

1. Open **Settings → Network & internet**.
2. Click the active adapter (the one connected to the device, usually **Ethernet**).
3. Next to **IP assignment**, click **Edit** → choose **Manual** → toggle **IPv4** on.
4. Enter:
   - **IP address:** `10.77.0.1`
   - **Subnet mask:** `255.255.255.0`
   - **Gateway:** leave blank
   - **DNS:** leave blank
5. Save.

To verify, open a Command Prompt and run `ping 10.77.0.2`. You should see replies.

By default Topside sends MCU traffic to `10.77.0.2`. For a nonstandard setup, set `ROV_HOST` before launching Topside. Broadcast helpers default to `10.77.0.255` and can be overridden with `ROV_BROADCAST`.

### Ports used

| Port       | Direction | Purpose                       |
|------------|-----------|-------------------------------|
| `5000/tcp` | local     | Dashboard (browser → app)     |
| `12345/udp`| outbound  | Control commands → device     |
| `5002/udp` | inbound   | IMU telemetry                 |
| `5005/udp` | inbound   | MCU control telemetry         |
| `5006/udp` | inbound   | MCU log stream                |
| `5008/udp` | outbound  | MCU reset/system control      |
| `12346/udp`| inbound   | Resource monitor              |
| `6969/udp` | inbound   | RPi camera stream             |

If you have a firewall (Windows Defender or similar), allow inbound UDP on `5002`, `5005`, `5006`, `12346`, and `6969`.

## Troubleshooting

- **No video / no telemetry** — verify the static IP, then `ping 10.77.0.2`. If the ping fails, the network is the problem, not the app.
- **Settings don't persist between launches** — the config lives at `%LOCALAPPDATA%\Topside\data\config.json`. The installer only writes a starter file if it doesn't exist, so reinstalling won't wipe your settings.
- **Live data doesn't update** — launch from the Start Menu and check the console line that starts with `Using data directory:`. For the installer it should be `%LOCALAPPDATA%\Topside\data`; `data.json` in that folder should update as UDP telemetry arrives.
- **App window closes immediately** — launch from the Start Menu (not by double-clicking inside Program Files). If the console flashes and disappears, run `Topside.exe` from `cmd.exe` to see the error.
