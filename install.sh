#!/bin/bash
# Script para instalar todos os dotfiles usando stow

set -e

DOTFILES_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DOTFILES_DIR"

echo "📦 Instalando dotfiles com GNU Stow..."
echo ""

# Verificar se stow está instalado
if ! command -v stow &> /dev/null; then
    echo "❌ GNU Stow não está instalado!"
    echo "   Instale com: sudo pacman -S stow"
    exit 1
fi

# Lista de pacotes para instalar
PACKAGES=(
    "hyprland"
    "hypr"
    "kitty"
    "waybar"
    "wlogout"
    "starship"
    "zsh"
    "gtk-3.0"
    "gtk-4.0"
)

# Instalar cada pacote
for package in "${PACKAGES[@]}"; do
    if [ -d "$package" ]; then
        echo "📌 Instalando $package..."
        stow -t ~ "$package" 2>&1 | grep -v "BUG in find_stowed_path" || true
        echo "   ✓ $package instalado"
    else
        echo "   ⚠ $package não encontrado, pulando..."
    fi
done

echo ""
echo "✅ Instalação concluída!"
echo ""
echo "📝 Próximos passos:"
echo "   1. Verifique os symlinks criados: ls -la ~/.config/"
echo "   2. Ajuste caminhos absolutos se necessário (ex: hypr/hypr/hyprpaper.conf)"
echo "   3. Reinicie o Hyprland ou recarregue as configurações"
echo ""

