#!/bin/bash
# Script para bloquear a tela usando wlogout
# Abre o wlogout como tela de bloqueio (mantém aberto bloqueando a tela)

CONFIG_DIR="$HOME/.config/wlogout"

# Fecha qualquer instância anterior do wlogout (menu atual)
killall wlogout 2>/dev/null

# Pequeno delay para garantir que o wlogout anterior foi fechado
sleep 0.05

# Abre o wlogout como tela de bloqueio
# Ele ficará aberto bloqueando a tela até que o usuário pressione ESC ou clique fora
wlogout \
    --layout "$CONFIG_DIR/layout" \
    --css "$CONFIG_DIR/style.css" \
    --buttons-per-row 2 \
    --column-spacing 20 \
    --row-spacing 20 \
    --margin-left 400 \
    --margin-right 400 \
    --margin-top 200 \
    --margin-bottom 200 \
    --protocol layer-shell

