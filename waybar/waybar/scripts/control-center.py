#!/usr/bin/env python3
"""Native GTK panels for Wi-Fi and tasks."""
import json, os, re, subprocess, sys, threading, uuid
from datetime import date, datetime
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
.task-title { color: #1d1d1f; font-size: 15px; font-weight: 600; }
.badge { border-radius: 999px; padding: 3px 9px; font-size: 11px; font-weight: 700; }
.priority-high { background: #ffe3e3; color: #b42318; }
.priority-medium { background: #fff1cc; color: #8a5700; }
.priority-low { background: #e4efff; color: #175cd3; }
.overdue { color: #b42318; font-weight: 700; }
.due-soon { color: #8a5700; font-weight: 600; }
entry { background: #ffffff; color: #1d1d1f; caret-color: #1d1d1f; }
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
 PRIORITIES=("Baixa","Média","Alta")
 PRIORITY_KEYS=("low","medium","high")
 def __init__(self,app):
  super().__init__(app,"Tarefas")
  state=Path(os.environ.get("XDG_STATE_HOME",Path.home()/".local/state"))/"waybar";state.mkdir(parents=True,exist_ok=True)
  self.path=state/"tasks.json";self.legacy=state/"todo.txt";self.migrate()
  hero=Gtk.Box(spacing=12,css_classes=["card","hero"]);copy=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,hexpand=True)
  copy.append(Gtk.Label(label="Organize seu dia",xalign=0,css_classes=["panel-primary"]));copy.append(Gtk.Label(label="Prioridades e prazos em um só lugar",xalign=0,css_classes=["subtitle"]));hero.append(copy)
  add=Gtk.Button(label="＋ Nova tarefa",css_classes=["suggested-action","pill"]);add.connect("clicked",lambda *_:self.task_form());hero.append(add);self.box.append(hero)
  self.counter=Gtk.Label(xalign=0,css_classes=["subtitle"]);self.box.append(self.counter)
  self.list=Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE,css_classes=["card"]);self.box.append(Gtk.ScrolledWindow(vexpand=True,hscrollbar_policy=Gtk.PolicyType.NEVER,child=self.list));self.reload()
 def migrate(self):
  if self.path.exists():return
  old=[x.strip() for x in self.legacy.read_text().splitlines() if x.strip()] if self.legacy.exists() else []
  created=datetime.now().isoformat(timespec="seconds")
  self.path.write_text(json.dumps([{"id":str(uuid.uuid4()),"title":x,"created_at":created,"due_date":None,"priority":"medium"} for x in old],ensure_ascii=False,indent=2))
 def tasks(self):
  try:return json.loads(self.path.read_text())
  except (json.JSONDecodeError,OSError):return []
 def save(self,tasks):
  temp=self.path.with_suffix(".tmp");temp.write_text(json.dumps(tasks,ensure_ascii=False,indent=2));temp.replace(self.path);subprocess.run(["pkill","-RTMIN+8","waybar"],capture_output=True);self.reload()
 @staticmethod
 def order(task):
  due=task.get("due_date") or "9999-12-31";overdue=bool(task.get("due_date") and task["due_date"]<date.today().isoformat());rank={"high":0,"medium":1,"low":2}.get(task.get("priority"),1)
  return (not overdue,due,rank,task.get("created_at",""))
 def reload(self):
  while child:=self.list.get_first_child():self.list.remove(child)
  tasks=sorted(self.tasks(),key=self.order);overdue=sum(bool(x.get("due_date") and x["due_date"]<date.today().isoformat()) for x in tasks);n=len(tasks)
  summary=f"{n} tarefa{'s' if n!=1 else ''} pendente{'s' if n!=1 else ''}"+(f" · {overdue} vencida{'s' if overdue!=1 else ''}" if overdue else "");self.counter.set_text(summary)
  if not tasks:self.list.append(Gtk.Label(label="Tudo em dia!\nCrie uma tarefa para começar.",justify=Gtk.Justification.CENTER,margin_top=80,css_classes=["subtitle"]))
  for task in tasks:self.list.append(self.task_row(task))
 def task_row(self,task):
  row=Gtk.Box(spacing=10,css_classes=["row"]);done=Gtk.CheckButton(tooltip_text="Marcar como concluída");done.connect("toggled",lambda *_:self.remove(task["id"]));row.append(done)
  body=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=3,hexpand=True);top=Gtk.Box(spacing=7);top.append(Gtk.Label(label=task["title"],xalign=0,hexpand=True,wrap=True,css_classes=["task-title"]));priority=task.get("priority","medium");label={"high":"Alta","medium":"Média","low":"Baixa"}[priority];top.append(Gtk.Label(label=label,css_classes=["badge",f"priority-{priority}"]));body.append(top)
  created=datetime.fromisoformat(task["created_at"]).strftime("Criada em %d/%m/%Y") if task.get("created_at") else "Data de criação desconhecida";due=task.get("due_date")
  if due:
   due_date=date.fromisoformat(due);delta=(due_date-date.today()).days
   if delta<0:deadline=f"Vencida há {abs(delta)} dia{'s' if abs(delta)!=1 else ''}";css="overdue"
   elif delta==0:deadline="Vence hoje";css="due-soon"
   elif delta==1:deadline="Vence amanhã";css="due-soon"
   else:deadline=f"Prazo: {due_date.strftime('%d/%m/%Y')}";css="muted"
   meta=Gtk.Box(spacing=8);meta.append(Gtk.Label(label=created,xalign=0,css_classes=["muted"]));meta.append(Gtk.Label(label="•"));meta.append(Gtk.Label(label=deadline,xalign=0,css_classes=[css]));body.append(meta)
  else:body.append(Gtk.Label(label=f"{created}  •  Sem prazo",xalign=0,css_classes=["muted"]))
  row.append(body);row.append(icon_button("document-edit-symbolic","Editar",lambda *_:self.task_form(task)));row.append(icon_button("user-trash-symbolic","Excluir",lambda *_:self.confirm_delete(task)));return row
 def remove(self,task_id):self.save([x for x in self.tasks() if x["id"]!=task_id])
 def confirm_delete(self,task):
  dialog=Adw.AlertDialog(heading="Excluir tarefa?",body=task["title"]);dialog.add_response("cancel","Cancelar");dialog.add_response("delete","Excluir");dialog.set_response_appearance("delete",Adw.ResponseAppearance.DESTRUCTIVE);dialog.set_close_response("cancel");dialog.connect("response",lambda _d,r:self.remove(task["id"]) if r=="delete" else None);dialog.present(self)
 def task_form(self,task=None):
  editing=task is not None;dialog=Adw.AlertDialog(heading="Editar tarefa" if editing else "Nova tarefa",body="Defina o que importa e quando precisa estar pronto.")
  form=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=10,margin_top=10,margin_bottom=6,margin_start=6,margin_end=6)
  title=Gtk.Entry(placeholder_text="Título da tarefa",text=task["title"] if editing else "",activates_default=True);form.append(title)
  priority_row=Gtk.Box(spacing=10);priority_row.append(Gtk.Label(label="Prioridade",xalign=0,hexpand=True,css_classes=["panel-primary"]));priority=Gtk.DropDown.new_from_strings(self.PRIORITIES);priority.set_selected(self.PRIORITY_KEYS.index(task.get("priority","medium")) if editing else 1);priority_row.append(priority);form.append(priority_row)
  has_due=Gtk.CheckButton(label="Definir prazo",active=bool(task and task.get("due_date")));form.append(has_due);calendar=Gtk.Calendar(sensitive=has_due.get_active());form.append(calendar);has_due.connect("toggled",lambda b:calendar.set_sensitive(b.get_active()))
  if editing and task.get("due_date"):
   selected=date.fromisoformat(task["due_date"]);calendar.select_day(GLib.DateTime.new_local(selected.year,selected.month,selected.day,0,0,0))
  dialog.set_extra_child(form);dialog.add_response("cancel","Cancelar");dialog.add_response("save","Salvar");dialog.set_response_appearance("save",Adw.ResponseAppearance.SUGGESTED);dialog.set_default_response("save");dialog.set_close_response("cancel")
  def response(_dialog,action):
   value=re.sub(r"\s+"," ",title.get_text()).strip()
   if action!="save":return
   if not value:self.toast("Digite um título para a tarefa.");return
   selected=calendar.get_date();due=f"{selected.get_year():04d}-{selected.get_month():02d}-{selected.get_day_of_month():02d}" if has_due.get_active() else None;tasks=self.tasks()
   if editing:
    for current in tasks:
     if current["id"]==task["id"]:current.update(title=value,priority=self.PRIORITY_KEYS[priority.get_selected()],due_date=due)
   else:tasks.append({"id":str(uuid.uuid4()),"title":value,"created_at":datetime.now().isoformat(timespec="seconds"),"due_date":due,"priority":self.PRIORITY_KEYS[priority.get_selected()]})
   self.save(tasks)
  dialog.connect("response",response);dialog.present(self);GLib.idle_add(title.grab_focus)

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
