#!/bin/sh
# Script para copiar arquivos binários (imagens, assets SVG, etc.)

DOTFILES="$HOME/projects/dotfiles"
CONFIG="$HOME/.config"

echo "Copiando arquivos binários..."

# Assets do GTK-3.0
if [ -d "$CONFIG/gtk-3.0/assets" ]; then
    mkdir -p "$DOTFILES/gtk-3.0/assets"
    cp -r "$CONFIG/gtk-3.0/assets"/* "$DOTFILES/gtk-3.0/assets/"
    echo "✓ Assets do GTK-3.0 copiados"
fi

# Assets do GTK-4.0 (se existir)
if [ -d "$CONFIG/gtk-4.0/assets" ]; then
    mkdir -p "$DOTFILES/gtk-4.0/assets"
    cp -r "$CONFIG/gtk-4.0/assets"/* "$DOTFILES/gtk-4.0/assets/"
    echo "✓ Assets do GTK-4.0 copiados"
fi

# Imagens de arte do wlogout
if [ -d "$CONFIG/wlogout/art" ]; then
    mkdir -p "$DOTFILES/wlogout/art"
    cp -r "$CONFIG/wlogout/art"/* "$DOTFILES/wlogout/art/"
    echo "✓ Imagens de arte do wlogout copiadas"
fi

# Ícones do wlogout (se ainda não foram copiados)
if [ -d "$CONFIG/wlogout/icons" ] && [ ! -d "$DOTFILES/wlogout/icons" ]; then
    mkdir -p "$DOTFILES/wlogout/icons"
    cp -r "$CONFIG/wlogout/icons"/* "$DOTFILES/wlogout/icons/"
    echo "✓ Ícones do wlogout copiados"
fi

echo "Concluído!"

