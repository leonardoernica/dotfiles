#!/bin/bash
# Script wrapper para bloquear a tela
# Funciona com hyprlock ou swaylock como fallback

if command -v hyprlock &>/dev/null; then
    hyprlock
elif command -v swaylock &>/dev/null; then
    swaylock -f
else
    echo "Nenhum lock screen encontrado (hyprlock ou swaylock)" >&2
    exit 1
fi

