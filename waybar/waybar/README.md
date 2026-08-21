# Custom Waybar for Hyprland

A premium, modern Waybar configuration designed for Arch Linux + Hyprland, featuring a "Cyber-Glass" aesthetic and integrated productivity tools.

## Features

- **Modern Design**: Rounded "pill" modules, blur effects, and neon accents (Catppuccin Mocha inspired colors).
- **Productivity**: Native GTK task manager and Rofi application launcher.
- **Connectivity**: Native GTK Wi-Fi panel with connection, password and radio controls.
- **Hardware Monitoring**: CPU, RAM, Battery, and Network stats.
- **Hyprland Integration**: Workspaces with persistent indicators and window titles.
- **Interactive**: Clickable modules (Clock -> Calendar, Volume -> Pavucontrol).

## Prerequisites

Ensure you have the following installed:

- **Waybar** (v0.14.0+)
- **Rofi** (Application launcher)
- **GTK 4, libadwaita and PyGObject** (native Wi-Fi and task panels)
- **Nerd Fonts** (e.g., `ttf-jetbrains-mono-nerd`)
- **Pavucontrol** (For volume control)
- **Network Manager** (`nm-connection-editor` for Wifi menu)
- **Blueman** (`blueman-manager` for Bluetooth menu)

## Installation

1.  **Backup existing config**:
    ```bash
    mv ~/.config/waybar ~/.config/waybar.bak
    ```

2.  **Install using Stow** (recommended):
    If you're using this dotfiles repository with stow:
    ```bash
    cd ~/projects/dotfiles
    stow -t ~ waybar
    ```
    
    **Or copy files manually**:
    Copy the contents of this directory to `~/.config/waybar`:
    ```bash
    cp -r waybar/waybar/* ~/.config/waybar/
    ```

3.  **Make script executable**:
    (If you copied, ensure the script is executable)
    ```bash
    chmod +x ~/.config/waybar/scripts/todo.sh ~/.config/waybar/scripts/control-center.py
    ```

4.  **Reload Waybar**:
    ```bash
    killall waybar
    waybar &
    ```

## Configuration

### Modules
- **Left**: Rofi Menu, Workspaces (Page Navigator style), Window Title.
- **Center**: Clock & Date.
- **Right**: To-Do (Click to manage), Hardware Group, Connectivity Group, Media Group, Battery.

### Customization
- **Colors**: Edit `style.css` to change the color palette.
- **Modules**: Edit `config.jsonc` to add/remove modules.

## Troubleshooting

- **Icons missing?** Make sure you have a Nerd Font installed and set in `style.css`.
- **Launcher not opening?** Ensure `rofi` is installed (`sudo pacman -S rofi`).
- **Wi-Fi or To-Do not opening?** Install `python-gobject gtk4 libadwaita`; NetworkManager must also be running for Wi-Fi.
- **Wifi/Bluetooth click not working?** Ensure `nm-connection-editor` and `blueman` are installed.
