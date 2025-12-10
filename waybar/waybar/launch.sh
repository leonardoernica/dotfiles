#!/bin/bash

# Terminate already running bar instances
killall -q waybar

# Wait until the processes have been shut down
while pgrep -x waybar >/dev/null; do sleep 1; done

# Fix for Hyprland IPC
# Ensure the signature is available if running under Hyprland
if [ -z "$HYPRLAND_INSTANCE_SIGNATURE" ]; then
    if [ -d "$XDG_RUNTIME_DIR/hypr" ]; then
        export HYPRLAND_INSTANCE_SIGNATURE=$(ls -1 $XDG_RUNTIME_DIR/hypr | grep -v .lock | head -n 1)
    elif [ -d "/tmp/hypr" ]; then
        export HYPRLAND_INSTANCE_SIGNATURE=$(ls -1 /tmp/hypr | grep -v .lock | head -n 1)
    fi
fi

# Launch Waybar
echo "Starting Waybar..."
waybar &

# Pre-warm wofi for instant WiFi menu (loads GTK libs in background)
(sleep 2 && echo "" | timeout 0.1 wofi --dmenu --width 1 --height 1 2>/dev/null) &
