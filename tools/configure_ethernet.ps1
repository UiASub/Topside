param(
    [string]$InterfaceAlias = $env:TOPSIDE_ETHERNET_ALIAS,
    [string]$IPAddress = "10.77.0.1",
    [int]$PrefixLength = 24
)

$ErrorActionPreference = "Stop"

function Test-Administrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Get-TargetAdapter {
    param([string]$Alias)

    if ($Alias) {
        $adapter = Get-NetAdapter -Name $Alias -ErrorAction SilentlyContinue
        if (-not $adapter) {
            throw "No network adapter named '$Alias' was found."
        }
        return $adapter
    }

    $ethernet = Get-NetAdapter -Name "Ethernet" -ErrorAction SilentlyContinue
    if ($ethernet) {
        return $ethernet
    }

    $wiredAdapters = @(
        Get-NetAdapter -Physical |
            Where-Object {
                $_.Status -eq "Up" -and
                $_.InterfaceDescription -notmatch "Wireless|Wi-Fi|WiFi|Bluetooth|Loopback|Virtual|VPN"
            }
    )

    if ($wiredAdapters.Count -eq 1) {
        return $wiredAdapters[0]
    }

    $names = ($wiredAdapters | ForEach-Object { $_.Name }) -join "', '"
    if ($names) {
        throw "Could not choose an adapter automatically. Re-run with -InterfaceAlias '<name>'. Active wired adapters: '$names'."
    }

    throw "No active wired Ethernet adapter was found. Connect the MCU Ethernet adapter or pass -InterfaceAlias '<name>'."
}

if (-not (Test-Administrator)) {
    throw "Administrator privileges are required to configure a network adapter."
}

$adapter = Get-TargetAdapter -Alias $InterfaceAlias
$interfaceIndex = $adapter.ifIndex

Write-Host "Configuring adapter '$($adapter.Name)' to $IPAddress/$PrefixLength..."

Set-NetIPInterface -InterfaceIndex $interfaceIndex -AddressFamily IPv4 -Dhcp Disabled

$existingAddress = Get-NetIPAddress -InterfaceIndex $interfaceIndex -AddressFamily IPv4 -IPAddress $IPAddress -ErrorAction SilentlyContinue
if ($existingAddress) {
    if ($existingAddress.PrefixLength -ne $PrefixLength) {
        Remove-NetIPAddress -InterfaceIndex $interfaceIndex -AddressFamily IPv4 -IPAddress $IPAddress -Confirm:$false
        New-NetIPAddress -InterfaceIndex $interfaceIndex -IPAddress $IPAddress -PrefixLength $PrefixLength | Out-Null
    }
} else {
    New-NetIPAddress -InterfaceIndex $interfaceIndex -IPAddress $IPAddress -PrefixLength $PrefixLength | Out-Null
}

Get-NetIPAddress -InterfaceIndex $interfaceIndex -AddressFamily IPv4 |
    Where-Object {
        $_.IPAddress -ne $IPAddress -and
        $_.IPAddress -notlike "169.254.*" -and
        $_.IPAddress -ne "127.0.0.1"
    } |
    Remove-NetIPAddress -Confirm:$false

Get-NetRoute -InterfaceIndex $interfaceIndex -DestinationPrefix "0.0.0.0/0" -ErrorAction SilentlyContinue |
    Remove-NetRoute -Confirm:$false

Set-DnsClientServerAddress -InterfaceIndex $interfaceIndex -ResetServerAddresses

Write-Host "Adapter '$($adapter.Name)' is configured for Topside."
