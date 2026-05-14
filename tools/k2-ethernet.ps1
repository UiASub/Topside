param(
    [ValidateSet("up", "down", "status")]
    [string]$Action = "up",
    [string]$HostIp = "10.77.0.1",
    [string]$McuIp = "10.77.0.2",
    [int]$PrefixLength = 24
)

$ErrorActionPreference = "Stop"
$StateDir = Join-Path ([Environment]::GetFolderPath("LocalApplicationData")) "Topside"
$StatePath = Join-Path $StateDir "k2-ethernet-state.json"

function Test-IsAdmin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Get-AdapterScore {
    param($Adapter)

    $score = 0
    $description = "$($Adapter.InterfaceDescription) $($Adapter.Name)"

    if ($Adapter.HardwareInterface) { $score += 20 }
    if ($Adapter.Status -eq "Up") { $score += 20 }
    if ($description -match "USB|CDC|Realtek|QinHeng|ASIX|Ethernet Adapter") { $score += 100 }
    if ($description -match "Wi-Fi|Wireless|Bluetooth|Loopback|Virtual|Hyper-V|VPN|TAP|Docker") { $score -= 200 }

    try {
        $pnp = Get-PnpDevice -InstanceId $Adapter.PnPDeviceID -ErrorAction Stop
        if ($pnp.InstanceId -match "^USB\\") { $score += 80 }
        if ($pnp.FriendlyName -match "USB|Ethernet") { $score += 20 }
    } catch {
        # PnP metadata is helpful but not required.
    }

    return $score
}

function Select-K2Adapter {
    $adapters = Get-NetAdapter -Physical |
        Where-Object {
            $_.InterfaceDescription -notmatch "Wi-Fi|Wireless|Bluetooth" -and
            $_.Status -ne "Disabled"
        } |
        ForEach-Object {
            [pscustomobject]@{
                Adapter = $_
                Score = Get-AdapterScore $_
            }
        } |
        Where-Object { $_.Score -gt -100 } |
        Sort-Object Score -Descending

    if (-not $adapters) {
        throw "No physical Ethernet adapters found."
    }

    Write-Host "Select Ethernet interface for K2 direct link:"
    for ($i = 0; $i -lt $adapters.Count; $i++) {
        $adapter = $adapters[$i].Adapter
        $suffix = if ($i -eq 0) { " (recommended)" } else { "" }
        Write-Host ("  {0}) {1} [{2}] {3}{4}" -f ($i + 1), $adapter.Name, $adapter.Status, $adapter.InterfaceDescription, $suffix)
    }

    $choice = Read-Host "Interface [1]"
    if ([string]::IsNullOrWhiteSpace($choice)) {
        $choice = "1"
    }
    $parsedChoice = 0
    if (-not [int]::TryParse($choice, [ref]$parsedChoice)) {
        throw "Invalid selection: $choice"
    }

    $index = $parsedChoice - 1
    if ($index -lt 0 -or $index -ge $adapters.Count) {
        throw "Invalid selection: $choice"
    }

    return $adapters[$index].Adapter
}

function Get-AdapterKey {
    param($Adapter)

    if ($Adapter.InterfaceGuid) {
        return $Adapter.InterfaceGuid.ToString()
    }
    if ($Adapter.PnPDeviceID) {
        return $Adapter.PnPDeviceID
    }
    return "$($Adapter.Name)|$($Adapter.MacAddress)"
}

function Get-K2State {
    if (-not (Test-Path $StatePath)) {
        return $null
    }

    try {
        return Get-Content -Raw -Path $StatePath | ConvertFrom-Json
    } catch {
        Write-Warning "Could not read saved K2 Ethernet state from $StatePath."
        return $null
    }
}

function Save-K2State {
    param($Adapter)

    $adapterKey = Get-AdapterKey $Adapter
    $existing = Get-K2State
    if ($existing -and $existing.AdapterKey -eq $adapterKey) {
        return
    }

    $ipInterface = Get-NetIPInterface -InterfaceIndex $Adapter.ifIndex -AddressFamily IPv4 -ErrorAction Stop
    New-Item -ItemType Directory -Force -Path $StateDir | Out-Null
    [pscustomobject]@{
        AdapterKey = $adapterKey
        Name = $Adapter.Name
        Dhcp = $ipInterface.Dhcp.ToString()
        SavedAt = (Get-Date).ToString("o")
    } | ConvertTo-Json | Set-Content -Encoding UTF8 -Path $StatePath
}

function Restore-K2State {
    param($Adapter)

    $state = Get-K2State
    if (-not $state) {
        Write-Warning "No saved K2 Ethernet state found. Leaving DHCP/static configuration unchanged."
        return
    }

    $adapterKey = Get-AdapterKey $Adapter
    if ($state.AdapterKey -ne $adapterKey) {
        Write-Warning "Saved K2 Ethernet state is for '$($state.Name)', not '$($Adapter.Name)'. Leaving DHCP/static configuration unchanged."
        return
    }

    if ($state.Dhcp -eq "Enabled") {
        Set-NetIPInterface -InterfaceIndex $Adapter.ifIndex -AddressFamily IPv4 -Dhcp Enabled | Out-Null
        Write-Host "Restored DHCP on $($Adapter.Name)."
    } else {
        Write-Host "Leaving DHCP disabled on $($Adapter.Name), matching the state before K2 setup."
    }

    Remove-Item -Path $StatePath -ErrorAction SilentlyContinue
}

function Remove-K2Address {
    param($Adapter)

    Get-NetIPAddress -InterfaceIndex $Adapter.ifIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object { $_.IPAddress -eq $HostIp } |
        Remove-NetIPAddress -Confirm:$false -ErrorAction SilentlyContinue
}

function Set-K2Link {
    if (-not (Test-IsAdmin)) {
        throw "Run this script from an Administrator PowerShell session."
    }

    $adapter = Select-K2Adapter

    Save-K2State $adapter
    Remove-K2Address $adapter
    Set-NetIPInterface -InterfaceIndex $adapter.ifIndex -AddressFamily IPv4 -Dhcp Disabled | Out-Null
    New-NetIPAddress -InterfaceIndex $adapter.ifIndex -IPAddress $HostIp -PrefixLength $PrefixLength | Out-Null

    Write-Host "Configured $($adapter.Name) as $HostIp/$PrefixLength for K2 direct link."
    Test-K2Ping
    Test-Mcumgr
}

function Clear-K2Link {
    if (-not (Test-IsAdmin)) {
        throw "Run this script from an Administrator PowerShell session."
    }

    $adapter = Select-K2Adapter
    Remove-K2Address $adapter
    Write-Host "Removed $HostIp from $($adapter.Name)."
    Restore-K2State $adapter
}

function Show-K2Status {
    Get-NetAdapter | Format-Table -AutoSize Name, Status, LinkSpeed, InterfaceDescription
    Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object { $_.IPAddress -eq $HostIp -or $_.IPAddress -eq $McuIp } |
        Format-Table -AutoSize InterfaceAlias, IPAddress, PrefixLength
    Test-Mcumgr
}

function Test-K2Ping {
    Write-Host "Checking MCU at $McuIp..."
    if (Test-Connection -ComputerName $McuIp -Count 2 -Quiet) {
        Write-Host "MCU responded at $McuIp."
    } else {
        Write-Warning "MCU did not respond to ping at $McuIp. The Ethernet cable may be disconnected, the MCU may be off, or ICMP may be unavailable."
    }
}

function Test-Mcumgr {
    if (Get-Command mcumgr -ErrorAction SilentlyContinue) {
        mcumgr version
        return
    }

    Write-Warning "mcumgr is not installed or not on PATH. Install Go, run 'go install github.com/apache/mynewt-mcumgr-cli/mcumgr@latest', and make sure `$env:USERPROFILE\go\bin is on PATH."
}

switch ($Action) {
    "up" { Set-K2Link }
    "down" { Clear-K2Link }
    "status" { Show-K2Status }
}
