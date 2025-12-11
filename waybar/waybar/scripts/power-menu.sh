#!/bin/bash
# Power Menu Script - Maximum performance, zero delays
# Direct execution - no unnecessary checks or sleeps

CONFIG_DIR="$HOME/.config/wlogout"

if command -v wlogout &>/dev/null; then
    # Kill any existing instance immediately
    killall -q wlogout
    
    # Execute immediately - no sleeps, no waits, no delays
    exec wlogout \
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
else
    # Fallback to wofi
    STYLE="
    window {
        background-color: rgba(17, 17, 27, 0.92);
        border: 2px solid rgba(255, 255, 255, 0.08);
        border-radius: 20px;
    }
    #entry {
        padding: 16px 24px;
        border-radius: 14px;
        margin: 6px 0;
        background-color: rgba(255, 255, 255, 0.03);
        border: 1px solid rgba(255, 255, 255, 0.05);
    }
    #entry:selected {
        background-color: rgba(137, 180, 250, 0.15);
        border: 1px solid rgba(137, 180, 250, 0.4);
    }
    #text { color: #cdd6f4; font-size: 15px; }
    #outer-box { margin: 16px; }
    #input { display: none; }
    "
    echo "$STYLE" > /tmp/wofi-power.css
    
    CHOICE=$(printf "  Desligar\n󰜉  Reiniciar\n  Bloquear\n󰒲  Suspender" | \
        wofi --dmenu --prompt "Power" -i --width 250 --height 220 --style /tmp/wofi-power.css --cache-file /dev/null)
    
    case "$CHOICE" in
        *"Desligar"*) systemctl poweroff ;;
        *"Reiniciar"*) systemctl reboot ;;
        *"Bloquear"*) bash -c "$HOME/.config/wlogout/scripts/lock.sh" ;;
        *"Suspender"*) systemctl suspend ;;
    esac
fi
