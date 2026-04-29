param(
    [switch]$NewTerminal
)

$ErrorActionPreference = "Stop"

$RootDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $RootDir

function Test-Command {
    param([Parameter(Mandatory = $true)][string]$Name)
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

function Add-UvToPath {
    $paths = @(
        Join-Path $env:USERPROFILE ".local\bin"
        Join-Path $env:USERPROFILE ".cargo\bin"
    )

    foreach ($path in $paths) {
        if ((Test-Path -LiteralPath $path) -and ($env:Path -notlike "*$path*")) {
            $env:Path = "$path;$env:Path"
        }
    }
}

function Install-Uv {
    if (Test-Command uv) {
        return
    }

    Write-Host "Installing uv..."
    powershell -ExecutionPolicy Bypass -NoProfile -Command "irm https://astral.sh/uv/install.ps1 | iex"
    Add-UvToPath

    if (-not (Test-Command uv)) {
        throw "uv was installed, but it is not on PATH. Add %USERPROFILE%\.local\bin to PATH and try again."
    }
}

function Ensure-Environment {
    Install-Uv

    uv python find 3.12 *> $null
    if ($LASTEXITCODE -ne 0) {
        uv python install 3.12
    }

    if (-not (Test-Path -LiteralPath ".venv" -PathType Container)) {
        uv venv --python 3.12 .venv
    }

    uv sync --frozen --no-default-groups --inexact
}

function Start-AppInNewTerminal {
    $shell = if (Test-Command pwsh) { "pwsh" } else { "powershell" }
    $escapedRoot = $RootDir.Replace("'", "''")
    $python = Join-Path $RootDir ".venv\Scripts\python.exe"
    $escapedPython = $python.Replace("'", "''")
    $command = "Set-Location -LiteralPath '$escapedRoot'; & '$escapedPython' app.py"

    Start-Process $shell -ArgumentList @(
        "-NoExit",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        $command
    )
}

Ensure-Environment

if ($NewTerminal) {
    Start-AppInNewTerminal
} else {
    & ".venv\Scripts\python.exe" app.py
}
