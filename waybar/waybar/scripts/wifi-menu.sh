#!/bin/bash
# WiFi Menu - Modern Glassmorphism Design
# Fast, beautiful, organized

# Custom wofi style for WiFi menu
STYLE="
window {
    background-color: rgba(30, 30, 46, 0.85);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 16px;
}
#outer-box {
    margin: 8px;
}
#input {
    background-color: rgba(255, 255, 255, 0.05);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 12px;
    padding: 12px 16px;
    color: #cdd6f4;
    font-size: 14px;
    margin-bottom: 8px;
}
#input:focus {
    border-color: rgba(137, 180, 250, 0.5);
    box-shadow: 0 0 10px rgba(137, 180, 250, 0.2);
}
#inner-box {
    background-color: transparent;
}
#scroll {
    margin: 0;
}
#text {
    color: #cdd6f4;
    font-size: 13px;
}
#entry {
    padding: 10px 14px;
    border-radius: 10px;
    margin: 2px 0;
}
#entry:selected {
    background-color: rgba(137, 180, 250, 0.2);
    border: 1px solid rgba(137, 180, 250, 0.3);
}
"

# Write temp style
STYLE_FILE="/tmp/wofi-wifi-style.css"
echo "$STYLE" > "$STYLE_FILE"

MENU="wofi --dmenu --prompt '󰤨  WiFi' -i --width 420 --height 400 --style $STYLE_FILE --cache-file /dev/null"

# Get current state
WIFI_ON=$(nmcli radio wifi)
CURRENT=$(nmcli -t -f active,ssid dev wifi list --rescan no 2>/dev/null | grep '^yes' | cut -d: -f2)
CURRENT_SIGNAL=$(nmcli -t -f active,signal dev wifi list --rescan no 2>/dev/null | grep '^yes' | cut -d: -f2)

# Build network list
get_networks() {
    nmcli -t -f SSID,SIGNAL,SECURITY dev wifi list --rescan no 2>/dev/null | while IFS=: read -r ssid signal security _; do
        [ -z "$ssid" ] && continue
        [ "$ssid" = "$CURRENT" ] && continue  # Skip current (shown separately)
        
        # Signal icon
        if [ "${signal:-0}" -ge 75 ]; then
            icon="󰤨"
        elif [ "${signal:-0}" -ge 50 ]; then
            icon="󰤥"
        elif [ "${signal:-0}" -ge 25 ]; then
            icon="󰤢"
        else
            icon="󰤟"
        fi
        
        # Security icon
        [ -n "$security" ] && [ "$security" != "--" ] && lock="󰒃" || lock="󰒄"
        
        printf "%s  %s  %s   %s%%\n" "$icon" "$lock" "$ssid" "$signal"
    done 2>/dev/null | sort -t'%' -k1 -rn | head -20
}

NETWORKS=$(get_networks)

# Build menu with sections
build_menu() {
    # Connected section
    if [ -n "$CURRENT" ]; then
        echo "━━━ CONECTADO ━━━━━━━━━━━━━━━"
        echo "✓  󰤨  $CURRENT   ${CURRENT_SIGNAL}%"
        echo "󰅖  Desconectar"
        echo ""
    fi
    
    # Actions section
    echo "━━━ AÇÕES ━━━━━━━━━━━━━━━━━━━"
    if [ "$WIFI_ON" = "disabled" ]; then
        echo "  Ligar WiFi"
    else
        echo "  Desligar WiFi"
    fi
    echo "󰑓  Atualizar Lista"
    echo "  Configurações"
    echo ""
    
    # Available networks
    if [ -n "$NETWORKS" ]; then
        echo "━━━ REDES DISPONÍVEIS ━━━━━━━"
        echo "$NETWORKS"
    fi
}

# Show menu
CHOICE=$(build_menu | eval "$MENU")
[ -z "$CHOICE" ] && exit 0

# Handle selection
case "$CHOICE" in
    *"━━━"*)
        # Header, ignore
        exit 0
        ;;
    "✓  󰤨  $CURRENT"*)
        notify-send "󰤨 WiFi" "Conectado a: $CURRENT\nSinal: ${CURRENT_SIGNAL}%"
        ;;
    "󰅖  Desconectar")
        nmcli connection down "$CURRENT" 2>/dev/null
        notify-send "󰤭 WiFi" "Desconectado de $CURRENT"
        ;;
    "  Ligar WiFi")
        nmcli radio wifi on
        notify-send "󰤨 WiFi" "WiFi ligado"
        sleep 2 && exec "$0" &
        ;;
    "  Desligar WiFi")
        nmcli radio wifi off
        notify-send "󰤭 WiFi" "WiFi desligado"
        ;;
    "󰑓  Atualizar Lista")
        notify-send "󰤨 WiFi" "Buscando redes..."
        nmcli device wifi rescan 2>/dev/null
        sleep 2
        exec "$0"
        ;;
    "  Configurações")
        nm-connection-editor &
        ;;
    "")
        # Empty line, ignore
        ;;
    *)
        # Network selection - extract SSID
        SSID=$(echo "$CHOICE" | sed 's/^[󰤨󰤥󰤢󰤟]  [󰒃󰒄]  //' | sed 's/   [0-9]*%$//')
        [ -z "$SSID" ] && exit 0
        
        # Check if saved network
        if nmcli -t -f NAME connection show | grep -qFx "$SSID"; then
            notify-send "󰤨 WiFi" "Conectando a $SSID..."
            if nmcli connection up "$SSID" 2>/dev/null; then
                notify-send "󰤨 WiFi" "✓ Conectado a $SSID"
            else
                notify-send "󰤭 WiFi" "✗ Falha ao conectar"
            fi
        else
            # New network
            SECURITY=$(nmcli -t -f SSID,SECURITY dev wifi list --rescan no 2>/dev/null | grep "^$SSID:" | cut -d: -f2 | head -n1)
            if [ -n "$SECURITY" ] && [ "$SECURITY" != "--" ]; then
                PASSWORD=$(echo "" | wofi --dmenu --prompt "󰒃 Senha para $SSID" --password --width 350 --style "$STYLE_FILE")
                [ -z "$PASSWORD" ] && exit 0
                notify-send "󰤨 WiFi" "Conectando a $SSID..."
                if nmcli device wifi connect "$SSID" password "$PASSWORD" 2>/dev/null; then
                    notify-send "󰤨 WiFi" "✓ Conectado a $SSID"
                else
                    notify-send "󰤭 WiFi" "✗ Senha incorreta"
                fi
            else
                notify-send "󰤨 WiFi" "Conectando a $SSID..."
                if nmcli device wifi connect "$SSID" 2>/dev/null; then
                    notify-send "󰤨 WiFi" "✓ Conectado a $SSID"
                else
                    notify-send "󰤭 WiFi" "✗ Falha ao conectar"
                fi
            fi
        fi
        ;;
esac
