# Custom Waybar for Hyprland

A premium, modern Waybar configuration designed for Arch Linux + Hyprland, featuring a "Cyber-Glass" aesthetic and integrated productivity tools.

## Features

- **Modern Design**: Rounded "pill" modules, blur effects, and neon accents (Catppuccin Mocha inspired colors).
- **Productivity**: Integrated To-Do list manager and Walker application launcher.
- **Hardware Monitoring**: CPU, RAM, Battery, and Network stats.
- **Hyprland Integration**: Workspaces with persistent indicators and window titles.
- **Interactive**: Clickable modules (Clock -> Calendar, Volume -> Pavucontrol).

## Prerequisites

Ensure you have the following installed:

- **Waybar** (v0.14.0+)
- **Walker** (Application launcher)
- **Nerd Fonts** (e.g., `ttf-jetbrains-mono-nerd`)
- **Pavucontrol** (For volume control)
- **Network Manager** (`nm-connection-editor` for Wifi menu)
- **Blueman** (`blueman-manager` for Bluetooth menu)
- **Terminal** (Kitty, Alacritty, or Foot supported for adding tasks)

## Installation

1.  **Backup existing config**:
    ```bash
    mv ~/.config/waybar ~/.config/waybar.bak
    ```

2.  **Copy files**:
    Copy the contents of this directory to `~/.config/waybar`:
    ```bash
    cp -r /home/lzin/projects/Waybar/* ~/.config/waybar/
    ```
    *Alternatively, you can symlink if you want to keep editing from the project folder:*
    ```bash
    ln -s /home/lzin/projects/Waybar ~/.config/waybar
    ```

3.  **Make script executable**:
    (If you copied, ensure the script is executable)
    ```bash
    chmod +x ~/.config/waybar/scripts/todo.sh
    ```

4.  **Reload Waybar**:
    ```bash
    killall waybar
    waybar &
    ```

## Configuration

### Modules
- **Left**: Walker Menu, Workspaces (Page Navigator style), Window Title.
- **Center**: Clock & Date.
- **Right**: To-Do (Click to manage), Hardware Group, Connectivity Group, Media Group, Battery.

### Customization
- **Colors**: Edit `style.css` to change the color palette.
- **Modules**: Edit `config.jsonc` to add/remove modules.

## Troubleshooting

- **Icons missing?** Make sure you have a Nerd Font installed and set in `style.css`.
- **Walker not opening?** Ensure `walker` is in your PATH.
- **To-Do list not opening?** The script uses `walker -d` for the menu. Ensure `walker` is installed.
- **Wifi/Bluetooth click not working?** Ensure `nm-connection-editor` and `blueman` are installed.
