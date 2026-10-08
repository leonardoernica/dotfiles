"""NetworkManager operations. Passwords travel over D-Bus, never argv."""
import getpass
import os
import subprocess
import uuid

import gi
gi.require_version("NM", "1.0")
from gi.repository import Gio, GLib, NM


class WifiError(RuntimeError):
    pass


def command(*args):
    try:
        result = subprocess.run(["nmcli", "--wait", "75", *args], text=True,
                                capture_output=True, timeout=85,
                                env={**os.environ, "LC_ALL": "C"})
    except subprocess.TimeoutExpired as exc:
        raise WifiError("A operação excedeu o tempo limite. Tente novamente.") from exc
    if result.returncode:
        raise WifiError(result.stderr.strip() or "Falha no NetworkManager.")
    return result.stdout


def fields(line):
    """Decode nmcli's escaped colon-separated fields without sentinel collisions."""
    parts, value, escaped = [], [], False
    for char in line:
        if escaped:
            value.append(char)
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == ":":
            parts.append("".join(value))
            value = []
        else:
            value.append(char)
    if escaped:
        value.append("\\")
    return parts + ["".join(value)]


def scan(force=False):
    enabled = command("radio", "wifi").strip() == "enabled"
    if not enabled:
        return False, []
    output = command("-t", "--escape", "yes", "-f",
                     "IN-USE,SSID,SIGNAL,SECURITY,BSSID,DEVICE", "device", "wifi",
                     "list", "--rescan", "yes" if force else "no")
    found = {}
    for line in output.splitlines():
        parts = fields(line)
        if len(parts) != 6:
            continue
        active, ssid, signal, security, bssid, device = parts
        if not ssid:
            continue
        net = dict(ssid=ssid, signal=int(signal or 0), security=security,
                   active=active == "*", bssid=bssid, device=device)
        key = (ssid, security, device)
        previous = found.get(key)
        if previous is None or (net["active"], net["signal"]) > (previous["active"], previous["signal"]):
            found[key] = net
    return True, sorted(found.values(), key=lambda n: (n["active"], n["signal"]), reverse=True)


def _call(path, interface, method, parameters):
    bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
    return bus.call_sync("org.freedesktop.NetworkManager", path, interface,
                         method, parameters, None, Gio.DBusCallFlags.NONE, 15000, None)


def _client():
    client = NM.Client.new(None)
    if not client.get_nm_running():
        raise WifiError("O serviço NetworkManager está indisponível.")
    return client


def profiles(client, net):
    device = client.get_device_by_iface(net["device"])
    if device is None:
        raise WifiError("O adaptador Wi-Fi não está disponível.")
    ap = next((a for a in device.get_access_points()
               if a.get_bssid() == net["bssid"]), None)
    matches = []
    for connection in client.get_connections():
        wireless = connection.get_setting_wireless()
        if wireless is None or wireless.get_ssid() is None:
            continue
        ssid = NM.utils_ssid_to_utf8(wireless.get_ssid().get_data())
        if ssid != net["ssid"] or not connection.get_setting_connection():
            continue
        if ap is not None and not ap.connection_valid(connection):
            continue
        if not device.connection_valid(connection):
            continue
        matches.append(connection)
    user = getpass.getuser()
    def rank(connection):
        setting = connection.get_setting_connection()
        own = setting.get_property("permissions") == [f"user:{user}:"]
        return own, setting.get_timestamp()
    return sorted(matches, key=rank, reverse=True)


def saved_uuid(net):
    client = _client()
    matches = profiles(client, net)
    return matches[0].get_uuid() if matches else None


def activate(net, connection_uuid):
    return command("connection", "up", "uuid", connection_uuid,
                   "ifname", net["device"], "ap", net["bssid"])


def disconnect(net):
    # Disconnect the selected device, independent of the profile's display name.
    return command("device", "disconnect", net["device"])


def connect(net, password):
    """Save a personal profile, or update an existing personal one, then activate."""
    security = net["security"]
    if "802.1X" in security or "EAP" in security or "WEP" in security:
        raise WifiError("Esta rede exige configurações avançadas de autenticação.")
    if security not in ("", "--") and "OWE" not in security:
        if password is None or not (8 <= len(password.encode("utf-8")) <= 63 or
                len(password) == 64 and all(c in "0123456789abcdefABCDEF" for c in password)):
            raise WifiError("A senha WPA deve ter de 8 a 63 bytes UTF-8 (ou 64 dígitos hexadecimais).")
    client = _client()
    matches = profiles(client, net)
    source = matches[0] if matches else None
    connection = NM.SimpleConnection.new_clone(source) if source else NM.SimpleConnection.new()
    connection.clear_secrets()
    setting = connection.get_setting_connection()
    if setting is None:
        setting = NM.SettingConnection.new()
        connection.add_setting(setting)
        setting.set_property("id", net["ssid"])
        setting.set_property("type", "802-11-wireless")
    user = getpass.getuser()
    own = source is not None and setting.get_property("permissions") == [f"user:{user}:"]
    if not own:
        setting.set_property("uuid", str(uuid.uuid4()))
    while setting.get_num_permissions():
        setting.remove_permission(0)
    setting.add_permission("user", user, None)
    setting.set_property("autoconnect", True)
    wireless = connection.get_setting_wireless()
    if wireless is None:
        wireless = NM.SettingWireless.new()
        connection.add_setting(wireless)
        wireless.set_property("ssid", GLib.Bytes.new(net["ssid"].encode()))
        wireless.set_property("mode", "infrastructure")
    if security not in ("", "--"):
        sec = NM.SettingWirelessSecurity.new()
        sec.set_property("key-mgmt", "owe" if "OWE" in security else
                         "sae" if "WPA3" in security and "WPA2" not in security else "wpa-psk")
        if password is not None:
            sec.set_property("psk", password)
        sec.set_property("psk-flags", NM.SettingSecretFlags.NONE)
        connection.add_setting(sec)
    else:
        connection.remove_setting(NM.SettingWirelessSecurity)
    if connection.get_setting_ip4_config() is None:
        ip4 = NM.SettingIP4Config.new(); ip4.set_property("method", "auto"); connection.add_setting(ip4)
    if connection.get_setting_ip6_config() is None:
        ip6 = NM.SettingIP6Config.new(); ip6.set_property("method", "auto"); connection.add_setting(ip6)
    connection.normalize()
    settings = connection.to_dbus(NM.ConnectionSerializationFlags.ALL)
    parameters = GLib.Variant.new_tuple(settings, GLib.Variant("u", 1), GLib.Variant("a{sv}", {}))
    if own:
        _call(source.get_path(), "org.freedesktop.NetworkManager.Settings.Connection", "Update2", parameters)
    else:
        _call("/org/freedesktop/NetworkManager/Settings", "org.freedesktop.NetworkManager.Settings", "AddConnection2", parameters)
    # No root-only settings are changed; the daemon saves this personal profile.
    return activate(net, connection.get_uuid())


def error_message(error):
    message = str(error)
    lower = message.lower()
    if any(word in lower for word in ("not authorized", "permission denied", "insufficient privileges")):
        return "Sem permissão para esta operação. Use um perfil pessoal nas configurações avançadas."
    if any(word in lower for word in ("secrets were required", "no secrets", "secrets-request")):
        return "A senha salva não foi aceita ou não está disponível. Digite a senha novamente."
    if "ip configuration could not be reserved" in lower:
        return "Não foi possível obter endereço IP. Verifique o DHCP do roteador ou repetidor."
    if "base network connection was interrupted" in lower:
        return "A conexão foi interrompida. Verifique a autenticação e tente novamente."
    if "could not be found" in lower:
        return "A rede saiu de alcance. Atualize a lista e tente novamente."
    return message
