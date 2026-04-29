#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

command_exists() {
    command -v "$1" >/dev/null 2>&1
}

detect_linux_distro() {
    if [[ ! -r /etc/os-release ]]; then
        echo "unknown"
        return
    fi

    # shellcheck disable=SC1091
    source /etc/os-release
    local distro="${ID:-unknown}"
    local like="${ID_LIKE:-}"

    case " $distro $like " in
        *" ubuntu "*|*" debian "*)
            echo "ubuntu"
            ;;
        *" fedora "*|*" rhel "*|*" centos "*)
            echo "fedora"
            ;;
        *" arch "*)
            echo "arch"
            ;;
        *)
            echo "$distro"
            ;;
    esac
}

missing_fetcher_help() {
    local distro="$1"

    echo "uv is not installed, and neither curl nor wget is available."
    case "$distro" in
        ubuntu)
            echo "Install curl with: sudo apt install curl"
            ;;
        fedora)
            echo "Install curl with: sudo dnf install curl"
            ;;
        arch)
            echo "Install curl with: sudo pacman -S curl"
            ;;
        *)
            echo "Install curl or wget, then run this script again."
            ;;
    esac
}

install_uv() {
    if command_exists uv; then
        return
    fi

    local platform
    platform="$(uname -s)"

    if [[ "$platform" == "Linux" ]]; then
        local distro
        distro="$(detect_linux_distro)"
        echo "Installing uv for Linux (${distro})..."
    else
        echo "Installing uv for ${platform}..."
    fi

    if command_exists curl; then
        curl -LsSf https://astral.sh/uv/install.sh | sh
    elif command_exists wget; then
        wget -qO- https://astral.sh/uv/install.sh | sh
    else
        missing_fetcher_help "${distro:-unknown}"
        exit 1
    fi

    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"

    if ! command_exists uv; then
        echo "uv was installed, but it is not on PATH. Add ~/.local/bin to PATH and try again."
        exit 1
    fi
}

ensure_environment() {
    install_uv

    if ! uv python find 3.12 >/dev/null 2>&1; then
        uv python install 3.12
    fi

    if [[ ! -d .venv ]]; then
        uv venv --python 3.12 .venv
    fi

    uv sync --frozen --no-default-groups --inexact
}

launch_in_new_terminal() {
    local quoted_root
    local quoted_python
    printf -v quoted_root "%q" "$ROOT_DIR"
    printf -v quoted_python "%q" "${ROOT_DIR}/.venv/bin/python"
    local command="cd ${quoted_root} && ${quoted_python} app.py"

    if command_exists gnome-terminal; then
        gnome-terminal -- bash -lc "${command}; exec bash"
    elif command_exists konsole; then
        konsole -e bash -lc "${command}; exec bash"
    elif command_exists xterm; then
        xterm -e bash -lc "${command}; exec bash"
    else
        echo "No supported terminal emulator found; running in this terminal instead."
        "${ROOT_DIR}/.venv/bin/python" app.py
    fi
}

ensure_environment

if [[ "${1:-}" == "--new-terminal" ]]; then
    launch_in_new_terminal
else
    "${ROOT_DIR}/.venv/bin/python" app.py
fi
