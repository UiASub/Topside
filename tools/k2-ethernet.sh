#!/usr/bin/env bash
set -euo pipefail

HOST_IP="${HOST_IP:-10.77.0.1}"
MCU_IP="${MCU_IP:-10.77.0.2}"
PREFIX="${PREFIX:-24}"
CON_PREFIX="${CON_PREFIX:-k2-direct}"
ACTION="${1:-up}"

usage() {
    echo "Usage: $0 [up|down|status]"
}

require_cmd() {
    if ! command -v "$1" >/dev/null 2>&1; then
        echo "Missing required command: $1" >&2
        exit 1
    fi
}

run_nmcli() {
    if nmcli "$@"; then
        return 0
    fi

    if [[ "${EUID}" -ne 0 ]] && command -v sudo >/dev/null 2>&1; then
        sudo nmcli "$@"
        return $?
    fi

    return 1
}

score_iface() {
    local iface="$1"
    local state="$2"
    local score=0
    local props=""
    local devpath=""

    props="$(udevadm info -q property -p "/sys/class/net/${iface}" 2>/dev/null || true)"
    devpath="$(readlink -f "/sys/class/net/${iface}/device" 2>/dev/null || true)"

    if grep -q '^ID_BUS=usb$' <<<"$props"; then
        score=$((score + 100))
    fi
    if [[ "$devpath" == *"/usb"* ]]; then
        score=$((score + 80))
    fi
    if [[ "$state" == "connected" || "$state" == "connecting"* ]]; then
        score=$((score + 20))
    fi
    if [[ "$(cat "/sys/class/net/${iface}/operstate" 2>/dev/null || true)" == "up" ]]; then
        score=$((score + 10))
    fi
    if [[ "$iface" == docker* || "$iface" == br-* || "$iface" == virbr* ]]; then
        score=$((score - 200))
    fi

    echo "$score"
}

describe_iface() {
    local iface="$1"
    local props=""
    props="$(udevadm info -q property -p "/sys/class/net/${iface}" 2>/dev/null || true)"

    local vendor model driver
    vendor="$(grep '^ID_VENDOR_FROM_DATABASE=' <<<"$props" | cut -d= -f2- || true)"
    [[ -z "$vendor" ]] && vendor="$(grep '^ID_VENDOR=' <<<"$props" | cut -d= -f2- || true)"
    model="$(grep '^ID_MODEL=' <<<"$props" | cut -d= -f2- | tr '_' ' ' || true)"
    driver="$(grep '^ID_NET_DRIVER=' <<<"$props" | cut -d= -f2- || true)"

    printf "%s %s %s" "$vendor" "$model" "$driver" | xargs
}

select_iface() {
    local rows=()
    local line iface type state score desc

    while IFS=: read -r iface type state _; do
        [[ "$type" == "ethernet" ]] || continue
        score="$(score_iface "$iface" "$state")"
        (( score > -100 )) || continue
        desc="$(describe_iface "$iface")"
        rows+=("${score}:${iface}:${state}:${desc}")
    done < <(nmcli -t -f DEVICE,TYPE,STATE device status)

    if (( ${#rows[@]} == 0 )); then
        echo "No Ethernet interfaces found." >&2
        exit 1
    fi

    mapfile -t rows < <(printf '%s\n' "${rows[@]}" | sort -rn)

    echo "Select Ethernet interface for K2 direct link:" >&2
    local idx=1
    for line in "${rows[@]}"; do
        IFS=: read -r score iface state desc <<<"$line"
        if (( idx == 1 )); then
            printf "  %d) %s [%s] %s (recommended)\n" "$idx" "$iface" "$state" "$desc" >&2
        else
            printf "  %d) %s [%s] %s\n" "$idx" "$iface" "$state" "$desc" >&2
        fi
        idx=$((idx + 1))
    done

    local choice
    read -r -p "Interface [1]: " choice
    choice="${choice:-1}"
    if ! [[ "$choice" =~ ^[0-9]+$ ]] || (( choice < 1 || choice > ${#rows[@]} )); then
        echo "Invalid selection: $choice" >&2
        exit 1
    fi

    IFS=: read -r _ iface _ _ <<<"${rows[$((choice - 1))]}"
    echo "$iface"
}

ping_mcu() {
    echo "Checking MCU at ${MCU_IP}..."
    if ping -c 2 -W 1 "$MCU_IP" >/dev/null 2>&1; then
        echo "MCU responded at ${MCU_IP}."
    else
        echo "Warning: MCU did not respond to ping at ${MCU_IP}." >&2
        echo "The Ethernet cable may be disconnected, the MCU may be off, or ICMP may be unavailable." >&2
    fi
}

check_mcumgr() {
    if command -v mcumgr >/dev/null 2>&1; then
        return
    fi

    echo "Warning: mcumgr is not installed or not on PATH." >&2
    echo "Install it with:" >&2
    echo "  sudo dnf install golang" >&2
    echo "  go install github.com/apache/mynewt-mcumgr-cli/mcumgr@latest" >&2
    echo "Then make sure ~/go/bin is on PATH." >&2
}

status_all() {
    nmcli device status
    echo
    nmcli connection show --active
    echo
    if command -v mcumgr >/dev/null 2>&1; then
        mcumgr version
    else
        check_mcumgr
    fi
}

up() {
    local iface="$1"
    local conn="${CON_PREFIX}-${iface}"

    if ! nmcli -t -f NAME connection show | grep -Fxq "$conn"; then
        run_nmcli connection add type ethernet ifname "$iface" con-name "$conn"
    fi

    run_nmcli connection modify "$conn" \
        connection.interface-name "$iface" \
        connection.autoconnect no \
        ipv4.method manual \
        ipv4.addresses "${HOST_IP}/${PREFIX}" \
        ipv4.gateway "" \
        ipv4.dns "" \
        ipv4.never-default yes \
        ipv6.method disabled

    run_nmcli connection up "$conn" ifname "$iface"

    echo "Configured ${iface} as ${HOST_IP}/${PREFIX} for K2 direct link."
    ping_mcu
    check_mcumgr
}

down() {
    local iface="$1"
    local conn="${CON_PREFIX}-${iface}"

    if nmcli -t -f NAME connection show | grep -Fxq "$conn"; then
        run_nmcli connection down "$conn" || true
        echo "Disconnected ${conn}."
    else
        echo "No ${conn} connection exists."
    fi
}

require_cmd nmcli
require_cmd udevadm

case "$ACTION" in
    up)
        up "$(select_iface)"
        ;;
    down)
        down "$(select_iface)"
        ;;
    status)
        status_all
        ;;
    -h|--help|help)
        usage
        ;;
    *)
        usage >&2
        exit 1
        ;;
esac
