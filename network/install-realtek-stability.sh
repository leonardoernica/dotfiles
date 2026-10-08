#!/usr/bin/env bash
# Hardware-specific workaround; connection passwords are not changed.
set -euo pipefail
if [[ $EUID != 0 ]]; then
    echo "Execute com sudo: sudo $0" >&2
    exit 1
fi
source_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
interface=""
for candidate in /sys/class/net/*; do
    if [[ $(basename -- "$(readlink -f -- "$candidate/device/driver")") == rtw88_8821ce ]]; then
        interface="$(basename -- "$candidate")"
        break
    fi
done
if [[ -z $interface ]]; then
    echo "Nenhum adaptador com driver rtw88_8821ce encontrado." >&2
    exit 1
fi
backup="/var/lib/dotfiles-wifi-backups/$(date +%Y%m%d-%H%M%S)"
install -d -m700 /var/lib/dotfiles-wifi-backups "$backup"
for destination in /etc/NetworkManager/conf.d/90-rtw88-stability.conf /etc/modprobe.d/rtw88-stability.conf; do
    if [[ -e $destination ]]; then cp -a -- "$destination" "$backup/"; fi
    install -Dm644 -- "$source_dir/$(basename -- "$destination")" "$destination"
done
nmcli general reload conf
iw dev "$interface" set power_save off
if [[ -w /sys/module/rtw88_core/parameters/disable_lps_deep ]]; then
    printf 'Y' > /sys/module/rtw88_core/parameters/disable_lps_deep
else
    echo "Reinicie para aplicar disable_lps_deep."
fi
echo "Economia desativada para $interface. Backup: $backup"
