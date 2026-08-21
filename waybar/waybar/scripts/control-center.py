#!/usr/bin/env python3
"""Native GTK panels for Wi-Fi and tasks."""
import os, re, subprocess, sys, threading
from pathlib import Path
import gi
gi.require_version("Gtk", "4.0"); gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk

CSS=b"""
window { background: #f5f5f7; color: #1d1d1f; }
headerbar { background: rgba(255,255,255,.94); box-shadow: 0 1px 0 rgba(0,0,0,.08); }
.panel { padding: 18px; }
.card { background: #fff; border: 1px solid rgba(0,0,0,.08); border-radius: 14px; }
.hero { padding: 16px; }
.title { font-size: 20px; font-weight: 700; }
.subtitle, .muted { color: #6e6e73; }
.row { padding: 11px 13px; border-bottom: 1px solid rgba(0,0,0,.06); }
.panel-primary { color: #1d1d1f; font-weight: 600; }
.connected { color: #14833b; font-weight: 600; }
.pill { border-radius: 999px; padding: 7px 14px; }
entry { border-radius: 10px; min-height: 38px; }
button { border-radius: 9px; }
"""

def run(*args): return subprocess.run(args,text=True,capture_output=True)
def background(work,done):
 def worker():
  try: result,error=work(),None
  except Exception as exc: result,error=None,exc
  GLib.idle_add(done,result,error)
 threading.Thread(target=worker,daemon=True).start()
def icon_button(icon,tip,callback):
 b=Gtk.Button(icon_name=icon,tooltip_text=tip); b.add_css_class("flat"); b.connect("clicked",callback); return b

class Window(Adw.ApplicationWindow):
 def __init__(self,app,title):
  super().__init__(application=app,title=title,default_width=520,default_height=620,resizable=False)
  view=Adw.ToolbarView(); header=Adw.HeaderBar(); header.set_title_widget(Gtk.Label(label=title,css_classes=["title"])); view.add_top_bar(header)
  self.box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=14,css_classes=["panel"]); self.toasts=Adw.ToastOverlay(child=self.box); view.set_content(self.toasts); self.set_content(view)
  keys=Gtk.EventControllerKey(); keys.connect("key-pressed",lambda _c,key,*_: self.close() or True if key==Gdk.KEY_Escape else False); self.add_controller(keys)
 def toast(self,text): self.toasts.add_toast(Adw.Toast(title=text,timeout=3))

class Wifi(Window):
 def __init__(self,app):
  super().__init__(app,"Wi-Fi"); self.changing=False
  hero=Gtk.Box(spacing=12,css_classes=["card","hero"]); labels=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,hexpand=True)
  labels.append(Gtk.Label(label="Conexão sem fio",xalign=0,css_classes=["panel-primary"])); self.status=Gtk.Label(label="Carregando…",xalign=0,css_classes=["subtitle"]); labels.append(self.status); hero.append(labels)
  self.toggle=Gtk.Switch(valign=Gtk.Align.CENTER); self.toggle.connect("state-set",self.toggle_wifi); hero.append(self.toggle); self.box.append(hero)
  heading=Gtk.Box(spacing=8); heading.append(Gtk.Label(label="Redes disponíveis",xalign=0,hexpand=True,css_classes=["panel-primary"])); self.spin=Gtk.Spinner(); heading.append(self.spin); heading.append(icon_button("view-refresh-symbolic","Atualizar",lambda *_:self.refresh(True))); self.box.append(heading)
  self.list=Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE,css_classes=["card"]); self.box.append(Gtk.ScrolledWindow(vexpand=True,hscrollbar_policy=Gtk.PolicyType.NEVER,child=self.list))
  advanced=Gtk.Button(label="Configurações avançadas",css_classes=["pill"]); advanced.connect("clicked",lambda *_:subprocess.Popen(["nm-connection-editor"])); self.box.append(advanced); self.refresh()
 def toggle_wifi(self,_switch,state):
  if self.changing:return False
  background(lambda:run("nmcli","radio","wifi","on" if state else "off"),lambda *_:self.refresh()); return False
 def refresh(self,force=False): self.spin.start(); self.status.set_text("Procurando redes…"); background(lambda:self.scan(force),self.show)
 @staticmethod
 def scan(force=False):
  enabled=run("nmcli","radio","wifi").stdout.strip()=="enabled"
  if not enabled:return enabled,[]
  if force:run("nmcli","device","wifi","rescan")
  output=run("nmcli","-t","--escape","yes","-f","IN-USE,SSID,SIGNAL,SECURITY","device","wifi","list","--rescan","no").stdout
  found=[]; seen=set()
  for line in output.splitlines():
   safe=line.replace(r"\\","__BS__").replace(r"\:","__COLON__"); parts=safe.split(":",3)
   if len(parts)!=4:continue
   active,ssid,signal,security=parts; ssid=ssid.replace("__COLON__",":").replace("__BS__","\\")
   if not ssid or ssid in seen:continue
   seen.add(ssid); found.append(dict(ssid=ssid,signal=int(signal or 0),security=security,active=active=="*"))
  return enabled,sorted(found,key=lambda n:n["signal"],reverse=True)
 def show(self,result,error):
  self.spin.stop()
  if error:self.status.set_text("NetworkManager indisponível");return False
  enabled,networks=result; self.changing=True; self.toggle.set_active(enabled); self.changing=False
  while child:=self.list.get_first_child():self.list.remove(child)
  if not enabled:self.status.set_text("Wi-Fi desligado");return False
  current=next((n["ssid"] for n in networks if n["active"]),None); self.status.set_text(f"Conectado a {current}" if current else "Não conectado")
  for net in networks:
   row=Gtk.ListBoxRow(activatable=True,css_classes=["row"]); content=Gtk.Box(spacing=12)
   signal_icon="󰤨" if net["signal"]>=70 else "󰤥" if net["signal"]>=40 else "󰤟"; content.append(Gtk.Label(label=signal_icon))
   labels=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,hexpand=True); labels.append(Gtk.Label(label=net["ssid"],xalign=0,max_width_chars=34,css_classes=["panel-primary"])); detail="Conectado" if net["active"] else f'{net["signal"]}% · {"Protegida" if net["security"] not in ("","--") else "Aberta"}'; labels.append(Gtk.Label(label=detail,xalign=0,css_classes=["connected" if net["active"] else "muted"])); content.append(labels)
   if net["security"] not in ("","--"):content.append(Gtk.Image.new_from_icon_name("system-lock-screen-symbolic"))
   row.set_child(content); row.connect("activate",self.select,net); self.list.append(row)
  return False
 def select(self,_row,net):
  if net["active"]:background(lambda:run("nmcli","connection","down","id",net["ssid"]),lambda *_:self.refresh());return
  def saved_done(result,_error):
   if result.returncode==0:self.refresh();return False
   if net["security"] in ("","--"):self.connect_network(net,None);return False
   dialog=Adw.AlertDialog(heading=f'Conectar a “{net["ssid"]}”',body="Digite a senha da rede."); password=Gtk.PasswordEntry(show_peek_icon=True,activates_default=True,margin_top=8,margin_bottom=8,margin_start=8,margin_end=8); dialog.set_extra_child(password); dialog.add_response("cancel","Cancelar");dialog.add_response("connect","Conectar");dialog.set_response_appearance("connect",Adw.ResponseAppearance.SUGGESTED);dialog.set_default_response("connect");dialog.set_close_response("cancel");dialog.connect("response",lambda _d,r:self.connect_network(net,password.get_text()) if r=="connect" else None);dialog.present(self);return False
  background(lambda:run("nmcli","connection","up","id",net["ssid"]),saved_done)
 def connect_network(self,net,password):
  self.status.set_text(f'Conectando a {net["ssid"]}…')
  def work():
   args=["nmcli","device","wifi","connect",net["ssid"]]
   if password:args += ["password",password]
   return run(*args)
  def done(result,error):
   if error or result.returncode:self.toast("Não foi possível conectar. Confira a senha.")
   self.refresh()
  background(work,done)

class Todo(Window):
 def __init__(self,app):
  super().__init__(app,"Tarefas"); state=Path(os.environ.get("XDG_STATE_HOME",Path.home()/".local/state"))/"waybar";state.mkdir(parents=True,exist_ok=True);self.path=state/"todo.txt";self.path.touch()
  compose=Gtk.Box(spacing=8,css_classes=["card","hero"]);self.entry=Gtk.Entry(placeholder_text="O que precisa ser feito?",hexpand=True);self.entry.connect("activate",self.add);compose.append(self.entry);button=Gtk.Button(label="Adicionar",css_classes=["suggested-action"]);button.connect("clicked",self.add);compose.append(button);self.box.append(compose)
  self.counter=Gtk.Label(xalign=0,css_classes=["subtitle"]);self.box.append(self.counter);self.list=Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE,css_classes=["card"]);self.box.append(Gtk.ScrolledWindow(vexpand=True,hscrollbar_policy=Gtk.PolicyType.NEVER,child=self.list));self.reload();GLib.idle_add(self.entry.grab_focus)
 def tasks(self):return [x.strip() for x in self.path.read_text().splitlines() if x.strip()]
 def save(self,tasks):self.path.write_text("".join(f"{x}\n" for x in tasks));subprocess.run(["pkill","-RTMIN+8","waybar"],capture_output=True);self.reload()
 def reload(self):
  while child:=self.list.get_first_child():self.list.remove(child)
  tasks=self.tasks();n=len(tasks);self.counter.set_text(f"{n} tarefa{'s' if n!=1 else ''} pendente{'s' if n!=1 else ''}")
  if not tasks:self.list.append(Gtk.Label(label="Tudo em dia!\nAdicione uma tarefa acima.",justify=Gtk.Justification.CENTER,margin_top=80,css_classes=["subtitle"]))
  for i,task in enumerate(tasks):
   row=Gtk.Box(spacing=10,css_classes=["row"]);done=Gtk.CheckButton(tooltip_text="Concluir");done.connect("toggled",lambda _b,index=i:self.delete(index));row.append(done);row.append(Gtk.Label(label=task,xalign=0,hexpand=True,wrap=True));row.append(icon_button("document-edit-symbolic","Editar",lambda _b,index=i:self.edit(index)));row.append(icon_button("user-trash-symbolic","Excluir",lambda _b,index=i:self.delete(index)));self.list.append(row)
 def add(self,*_):
  task=re.sub(r"\s+"," ",self.entry.get_text()).strip()
  if not task:self.entry.grab_focus();return
  tasks=self.tasks();tasks.append(task);self.save(tasks);self.entry.set_text("");self.entry.grab_focus()
 def delete(self,index):
  tasks=self.tasks()
  if index<len(tasks):tasks.pop(index);self.save(tasks)
 def edit(self,index):
  tasks=self.tasks();dialog=Adw.AlertDialog(heading="Editar tarefa");entry=Gtk.Entry(text=tasks[index],activates_default=True,margin_top=8,margin_bottom=8,margin_start=8,margin_end=8);dialog.set_extra_child(entry);dialog.add_response("cancel","Cancelar");dialog.add_response("save","Salvar");dialog.set_response_appearance("save",Adw.ResponseAppearance.SUGGESTED);dialog.set_default_response("save");dialog.set_close_response("cancel")
  def response(_d,action):
   value=re.sub(r"\s+"," ",entry.get_text()).strip();current=self.tasks()
   if action=="save" and value and index<len(current):current[index]=value;self.save(current)
  dialog.connect("response",response);dialog.present(self)

class App(Adw.Application):
 def __init__(self,mode):super().__init__(application_id=f"com.leonardoernica.Waybar.{mode.title()}",flags=Gio.ApplicationFlags.DEFAULT_FLAGS);self.mode=mode;self.window=None
 def do_activate(self):
  if not self.window:self.window=Wifi(self) if self.mode=="wifi" else Todo(self);self.window.connect("close-request",lambda *_:self.quit() or False)
  self.window.present()
def main():
 mode=sys.argv[1] if len(sys.argv)>1 else ""
 if mode not in ("wifi","todo"):return 2
 provider=Gtk.CssProvider();provider.load_from_data(CSS);Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(),provider,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION);return App(mode).run([sys.argv[0]])
if __name__=="__main__":raise SystemExit(main())
