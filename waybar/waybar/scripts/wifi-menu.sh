#!/bin/bash
# WiFi Menu Script - Simple and functional

# Get current connection
CURRENT=$(nmcli -t -f active,ssid dev wifi 2>/dev/null | grep '^yes:' | cut -d: -f2)

# Get WiFi status
WIFI_STATUS=$(nmcli radio wifi)

# Build menu
MENU_ITEMS=""
if [ "$WIFI_STATUS" = "enabled" ]; then
    if [ -n "$CURRENT" ]; then
        MENU_ITEMS+="Desconectar de $CURRENT\n"
        MENU_ITEMS+="━━━━━━━━━━━━━━━━━━\n"
    fi
    
    # List available networks
    while IFS=: read -r ssid signal security; do
        [ -z "$ssid" ] && continue
        [ "$ssid" = "$CURRENT" ] && continue
        MENU_ITEMS+="$ssid ($signal%)\n"
    done < <(nmcli -t -f SSID,SIGNAL,SECURITY dev wifi list --rescan no 2>/dev/null)
    
    MENU_ITEMS+="━━━━━━━━━━━━━━━━━━\n"
    MENU_ITEMS+="Desligar WiFi\n"
    MENU_ITEMS+="Atualizar\n"
    MENU_ITEMS+="Configurações"
else
    MENU_ITEMS="Ligar WiFi\nConfigurações"
fi

# Show menu
CHOICE=$(echo -e "$MENU_ITEMS" | wofi --dmenu --prompt "WiFi" --width 400 --height 500 -i 2>/dev/null)

[ -z "$CHOICE" ] && exit 0

case "$CHOICE" in
    "Ligar WiFi")
        nmcli radio wifi on
        notify-send "WiFi" "WiFi ligado"
        ;;
    "Desligar WiFi")
        nmcli radio wifi off
        notify-send "WiFi" "WiFi desligado"
        ;;
    "Desconectar de "*)
        nmcli connection down "$CURRENT" 2>/dev/null
        notify-send "WiFi" "Desconectado"
        ;;
    "Atualizar")
        nmcli device wifi rescan 2>/dev/null
        notify-send "WiFi" "Buscando redes..."
        sleep 2
        exec "$0"
        ;;
    "Configurações")
        nm-connection-editor &
        ;;
    *)
        # Extract SSID (remove signal percentage)
        SSID=$(echo "$CHOICE" | sed 's/ ([0-9]*%)$//')
        
        # Check if connection exists
        CONN_UUID=$(nmcli -t -f UUID,802-11-wireless.ssid connection show 2>/dev/null | grep ":$SSID$" | cut -d: -f1 | head -n1)
        
        if [ -n "$CONN_UUID" ]; then
            # Connect to existing connection
            notify-send "WiFi" "Conectando a $SSID..."
            if nmcli connection up "$CONN_UUID" 2>/dev/null; then
                notify-send "WiFi" "Conectado a $SSID"
            else
                notify-send "WiFi" "Falha ao conectar"
            fi
        else
            # New network - check security
            SECURITY=$(nmcli -t -f SSID,SECURITY dev wifi list --rescan no 2>/dev/null | grep "^$SSID:" | cut -d: -f2 | head -n1)
            
            if [ -n "$SECURITY" ] && [ "$SECURITY" != "--" ]; then
                # Ask for password
                PASSWORD=$(wofi --dmenu --password --prompt "Senha para $SSID" --width 350 2>/dev/null)
                [ -z "$PASSWORD" ] && exit 0
                
                notify-send "WiFi" "Conectando a $SSID..."
                if nmcli device wifi connect "$SSID" password "$PASSWORD" 2>/dev/null; then
                    notify-send "WiFi" "Conectado a $SSID"
                else
                    notify-send "WiFi" "Senha incorreta"
                fi
            else
                # Open network
                notify-send "WiFi" "Conectando a $SSID..."
                if nmcli device wifi connect "$SSID" 2>/dev/null; then
                    notify-send "WiFi" "Conectado a $SSID"
                else
                    notify-send "WiFi" "Falha ao conectar"
                fi
            fi
        fi
        ;;
esac
