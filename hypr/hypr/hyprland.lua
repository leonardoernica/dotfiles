-- Hyprland 0.56+ configuration
local terminal, file_manager, chatgpt = "kitty", "dolphin", "chatgpt"
local menu, main_mod = "rofi -show drun -show-icons", "SUPER"

hl.monitor({ output = "", mode = "preferred", position = "auto", scale = 1 })
hl.env("TERMINAL", terminal)
hl.env("NIXOS_OZONE_WL", "1")

hl.config({
    input = {
        kb_layout = "br", kb_model = "abnt2", follow_mouse = 1, sensitivity = 0,
        touchpad = {
            natural_scroll = true, disable_while_typing = true,
            tap_to_click = true, tap_and_drag = true, drag_lock = true,
            clickfinger_behavior = true, tap_button_map = "lrm", scroll_factor = 2.0,
        },
    },
    decoration = {
        rounding = 8, active_opacity = 1.0, inactive_opacity = 1.0,
        blur = { enabled = true, size = 3, passes = 1, new_optimizations = true },
        shadow = { enabled = false },
    },
    animations = { enabled = true },
})

hl.curve("overshot", { type = "bezier", points = { { 0.05, 0.9 }, { 0.1, 1.05 } } })
hl.animation({ leaf = "windows", enabled = true, speed = 3, bezier = "overshot", style = "slide" })
hl.animation({ leaf = "windowsOut", enabled = true, speed = 3, bezier = "default", style = "popin 80%" })
hl.animation({ leaf = "border", enabled = true, speed = 10, bezier = "default" })
hl.animation({ leaf = "fade", enabled = true, speed = 3, bezier = "default" })
hl.animation({ leaf = "workspaces", enabled = true, speed = 3, bezier = "overshot", style = "slidevert" })
hl.gesture({ fingers = 3, direction = "vertical", action = "workspace" })

hl.on("hyprland.start", function()
    hl.exec_cmd("waybar")
    hl.exec_cmd("hyprpaper")
    hl.exec_cmd("/usr/lib/polkit-kde-authentication-agent-1")
    -- Export the complete session environment before apps request portals.
    -- xdg-desktop-portal and XDPH are activated automatically through D-Bus.
    hl.exec_cmd("dbus-update-activation-environment --systemd --all")
    hl.exec_cmd(terminal)
    hl.exec_cmd("chromium", { workspace = "2 silent" })
    hl.exec_cmd(chatgpt, { workspace = "3 silent" })
end)

hl.window_rule({ name = "kitty-workspace", match = { class = "^kitty$" }, workspace = "1" })
hl.window_rule({ name = "chromium-workspace", match = { class = "^chromium$" }, workspace = "2" })
hl.window_rule({ name = "chatgpt-workspace", match = { class = "^Chatgpt$" }, workspace = "3" })
hl.layer_rule({
    name = "blur-logout", match = { namespace = "^(wlogout|logout_dialog)$" },
    blur = true, ignore_alpha = 0,
})

hl.bind(main_mod .. " + RETURN", hl.dsp.exec_cmd(terminal))
hl.bind(main_mod .. " + Q", hl.dsp.window.close())
hl.bind(main_mod .. " + M", hl.dsp.exit())
hl.bind(main_mod .. " + E", hl.dsp.exec_cmd(file_manager))
hl.bind(main_mod .. " + D", hl.dsp.exec_cmd(menu))
hl.bind(main_mod .. " + F", hl.dsp.window.fullscreen({ mode = 0 }))
hl.bind(main_mod .. " + V", hl.dsp.window.float({ action = "toggle" }))
hl.bind(main_mod .. " + P", hl.dsp.window.pseudo())
hl.bind(main_mod .. " + J", hl.dsp.layout("togglesplit"))
hl.bind(main_mod .. " + mouse:272", hl.dsp.window.drag(), { mouse = true })
hl.bind(main_mod .. " + mouse:273", hl.dsp.window.resize(), { mouse = true })
for workspace = 1, 10 do
    local key = workspace % 10
    hl.bind(main_mod .. " + " .. key, hl.dsp.focus({ workspace = workspace }))
    hl.bind(main_mod .. " + SHIFT + " .. key, hl.dsp.window.move({ workspace = workspace }))
end
hl.bind(main_mod .. " + SHIFT + S", hl.dsp.exec_cmd('grim -g "$(slurp)" - | wl-copy'))
hl.bind(main_mod .. " + PRINT", hl.dsp.exec_cmd("grim - | wl-copy"))
hl.bind("XF86MonBrightnessUp", hl.dsp.exec_cmd("brightnessctl set +10%"), { locked = true, repeating = true })
hl.bind("XF86MonBrightnessDown", hl.dsp.exec_cmd("brightnessctl set 10%-"), { locked = true, repeating = true })
hl.bind("XF86AudioRaiseVolume", hl.dsp.exec_cmd("wpctl set-volume -l 1 @DEFAULT_AUDIO_SINK@ 5%+"), { locked = true, repeating = true })
hl.bind("XF86AudioLowerVolume", hl.dsp.exec_cmd("wpctl set-volume @DEFAULT_AUDIO_SINK@ 5%-"), { locked = true, repeating = true })
hl.bind("XF86AudioMute", hl.dsp.exec_cmd("wpctl set-mute @DEFAULT_AUDIO_SINK@ toggle"), { locked = true })
hl.bind(main_mod .. " + SHIFT + R", hl.dsp.exec_cmd("hyprctl reload"))
