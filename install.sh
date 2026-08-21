#!/bin/bash
# Script para instalar todos os dotfiles via symlinks
set -e

DOTS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG="$HOME/.config"

stow_or_warn() {
    local target="$1" package="$2"
    if [ ! -d "$DOTS/$package" ]; then
        echo "   ⚠ $package não encontrado, pulando..."
        return
    fi
    if ! command -v stow &>/dev/null; then
        echo "   ⚠ stow não instalado (sudo pacman -S stow)"
        return
    fi
    echo "   Stow $package → $target"
    stow -t "$target" "$package" 2>&1 | grep -v "BUG in find_stowed_path" || true
}

symlink() {
    local src="$1" dst="$2"
    mkdir -p "$(dirname "$dst")"
    ln -sf "$src" "$dst"
    echo "   ✓ $(basename "$dst")"
}

echo "Instalando dotfiles..."
echo ""

# ── Pacotes com estrutura package/package_name/ → ~/.config/package_name/
# (usa stow -t ~/.config)
echo "[~/.config] kitty waybar wlogout gtk-3.0 gtk-4.0"
for pkg in kitty waybar wlogout gtk-3.0 gtk-4.0; do
    stow_or_warn "$CONFIG" "$pkg"
done

# Existing ~/.config/waybar directories may contain links created by an older
# version. Ensure every current helper is exposed, including newly added ones.
if [ -d "$DOTS/waybar/waybar/scripts" ]; then
    mkdir -p "$CONFIG/waybar/scripts"
    for script in "$DOTS"/waybar/waybar/scripts/*; do
        [ -f "$script" ] && symlink "$script" "$CONFIG/waybar/scripts/$(basename "$script")"
    done
fi

# ── Pacotes com estrutura package/.hidden/ → ~/
# (usa stow -t ~)
echo ""
echo "[~] starship zsh"
for pkg in starship zsh; do
    stow_or_warn "$HOME" "$pkg"
done

# ── Hypr: estrutura mista, symlinks manuais
echo ""
echo "[manual] hypr"
mkdir -p "$CONFIG/hypr" "$CONFIG/hyprland"
symlink "$DOTS/hypr/hypr/hyprland.conf"          "$CONFIG/hypr/hyprland.conf"
symlink "$DOTS/hypr/hypr/hyprland.lua"           "$CONFIG/hypr/hyprland.lua"
symlink "$DOTS/hypr/hypr/hyprpaper.conf"         "$CONFIG/hypr/hyprpaper.conf"
symlink "$DOTS/hypr/.config/hyprland/autostart.conf" "$CONFIG/hyprland/autostart.conf"
[ -d "$DOTS/hypr/.config/hyprlock" ] && symlink "$DOTS/hypr/.config/hyprlock" "$CONFIG/hyprlock"

# ── Libinput quirks (requer sudo) — botão direito físico do touchpad
echo ""
if [ -f "$DOTS/libinput/etc/libinput/local-overrides.quirks" ]; then
    read -rp "Instalar libinput quirk do touchpad? (requer sudo) [s/N] " ans
    if [[ "$ans" =~ ^[sS]$ ]]; then
        sudo install -Dm644 "$DOTS/libinput/etc/libinput/local-overrides.quirks" /etc/libinput/local-overrides.quirks
        echo "   ✓ Quirk instalado (reinicie para aplicar)"
    fi
fi

# ── SDDM (requer sudo)
echo ""
if [ -d "$DOTS/sddm" ] && command -v stow &>/dev/null; then
    read -rp "Instalar SDDM? (requer sudo) [s/N] " ans
    if [[ "$ans" =~ ^[sS]$ ]]; then
        sudo stow -t / sddm 2>&1 | grep -v "BUG in find_stowed_path" || true
        echo "   ✓ SDDM instalado (reinicie: sudo systemctl restart sddm)"
    fi
fi

echo ""
echo "Instalação concluída."
echo "  → Verifique: ls -la ~/.config/"
echo "  → Recarregue: hyprctl reload"
