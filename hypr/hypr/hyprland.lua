--=======================================
-- HYPRLAND CONFIG - Arch Linux Vaio FE15
-- Formato Lua para Hyprland 0.55+
--=======================================

local hl = require("hl")

local terminal    = "kitty"
local fileManager = "dolphin"
local menu        = "wofi --show drun"
local mainMod     = "SUPER"

-- -------------------------------------------------------
-- CONFIG GLOBAL
-- -------------------------------------------------------
hl.config(function(config)
    -- Monitor
    hl.monitor("", "preferred", "auto", 1)

    -- Teclado
    config.input.kb_layout  = "br"
    config.input.kb_model   = "abnt2"
    config.input.follow_mouse = 1
    config.input.sensitivity  = 0

    -- Touchpad
    config.input.touchpad.natural_scroll       = true
    config.input.touchpad.disable_while_typing = true
    config.input.touchpad["tap-to-click"]      = true
    config.input.touchpad["tap-and-drag"]      = true
    config.input.touchpad.drag_lock            = true
    config.input.touchpad.clickfinger_behavior = true
    config.input.touchpad.scroll_factor        = 2.0

    -- Env vars
    hl.env("TERMINAL",        "kitty")
    hl.env("NIXOS_OZONE_WL", "1")

    -- Decoração
    config.decoration.rounding         = 8
    config.decoration.active_opacity   = 1.0
    config.decoration.inactive_opacity = 1.0
    config.decoration.blur.enabled            = true
    config.decoration.blur.size               = 3
    config.decoration.blur.passes             = 1
    config.decoration.blur.new_optimizations  = true
    config.decoration.shadow.enabled          = false

    -- Animações
    config.animations.enabled = true
    hl.bezier("overshot", 0.05, 0.9, 0.1, 1.05)
    hl.animation("windows",      1, 3,  "overshot", "slide")
    hl.animation("windowsOut",   1, 3,  "default",  "popin 80%")
    hl.animation("border",       1, 10, "default")
    hl.animation("fade",         1, 3,  "default")
    hl.animation("workspaces",   1, 3,  "overshot", "slidevert")
end)

-- -------------------------------------------------------
-- AUTOSTART
-- -------------------------------------------------------
hl.exec_once("waybar")
hl.exec_once("hyprpaper")
hl.exec_once("/usr/lib/polkit-kde-authentication-agent-1")
hl.exec_once("dbus-update-activation-environment --systemd WAYLAND_DISPLAY XDG_CURRENT_DESKTOP")
hl.exec_once("/usr/lib/xdg-desktop-portal")
hl.exec_once("/usr/lib/xdg-desktop-portal-hyprland")
hl.exec_once("kitty")
hl.exec_once("[workspace 2 silent] chromium")
hl.exec_once("[workspace 3 silent] dolphin")

-- -------------------------------------------------------
-- REGRAS DE JANELA
-- -------------------------------------------------------
hl.windowrule("workspace 1", "match:class kitty")
hl.windowrule("workspace 2", "match:class chromium")
hl.windowrule("workspace 3", "match:class org.kde.dolphin")

-- -------------------------------------------------------
-- GESTOS
-- -------------------------------------------------------
hl.gesture(3, "vertical", "workspace")

-- -------------------------------------------------------
-- LAYER RULES
-- -------------------------------------------------------
hl.layerrule("blur on",      "match:namespace ^(wlogout|logout_dialog)$")
hl.layerrule("ignore_alpha 0", "match:namespace ^(wlogout|logout_dialog)$")

-- -------------------------------------------------------
-- ATALHOS DE TECLADO
-- -------------------------------------------------------

-- Aplicativos e Controles Básicos
hl.bind(mainMod, "RETURN", "exec",          terminal)
hl.bind(mainMod, "Q",      "killactive")
hl.bind(mainMod, "M",      "exit")
hl.bind(mainMod, "E",      "exec",          fileManager)
hl.bind(mainMod, "D",      "exec",          menu)
hl.bind(mainMod, "F",      "fullscreen",    0)

-- Controle de Janelas
hl.bind(mainMod,  "V", "togglefloating")
hl.bind(mainMod,  "P", "pseudo")
hl.bind(mainMod,  "J", "togglesplit")
hl.bindm(mainMod, "mouse:272", "movewindow")
hl.bindm(mainMod, "mouse:273", "resizewindow")

-- Workspaces 1-10
for i = 1, 9 do
    hl.bind(mainMod,              tostring(i), "workspace",     i)
    hl.bind(mainMod .. " SHIFT",  tostring(i), "movetoworkspace", i)
end
hl.bind(mainMod,             "0", "workspace",       10)
hl.bind(mainMod .. " SHIFT", "0", "movetoworkspace", 10)

-- Screenshots e Mídia
hl.bind(mainMod .. " SHIFT", "S",     "exec", 'grim -g "$(slurp)" - | wl-copy')
hl.bind(mainMod,             "PRINT", "exec", "grim - | wl-copy")
hl.bind("", "XF86MonBrightnessUp",   "exec", "brightnessctl set +10%")
hl.bind("", "XF86MonBrightnessDown", "exec", "brightnessctl set 10%-")
hl.bind("", "XF86AudioRaiseVolume",  "exec", "wpctl set-volume @DEFAULT_AUDIO_SINK@ 5%+")
hl.bind("", "XF86AudioLowerVolume",  "exec", "wpctl set-volume @DEFAULT_AUDIO_SINK@ 5%-")
hl.bind("", "XF86AudioMute",         "exec", "wpctl set-mute @DEFAULT_AUDIO_SINK@ toggle")
hl.bind(mainMod .. " SHIFT", "R",    "exec", "hyprctl reload")
