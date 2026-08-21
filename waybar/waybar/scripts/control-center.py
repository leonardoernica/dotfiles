#!/usr/bin/env python3
"""Native GTK panels for Wi-Fi and tasks."""
import json, os, re, subprocess, sys, threading, uuid
from datetime import date, datetime
from pathlib import Path
import gi
gi.require_version("Gtk", "4.0"); gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk

CSS=b"""
window { background: #111318; color: #f5f7fa; }
headerbar { background: rgba(24,27,34,.96); box-shadow: 0 1px 0 rgba(255,255,255,.08); }
.panel { padding: 18px; }
.card { background: #1b1e26; border: 1px solid rgba(255,255,255,.09); border-radius: 14px; }
.hero { padding: 16px; }
.title { font-size: 20px; font-weight: 700; }
.subtitle, .muted { color: #9ca3af; }
.row { padding: 11px 13px; border-bottom: 1px solid rgba(255,255,255,.07); }
.panel-primary { color: #f5f7fa; font-weight: 600; }
.connected { color: #4ade80; font-weight: 600; }
.pill { border-radius: 999px; padding: 7px 14px; }
entry { border-radius: 10px; min-height: 38px; }
button { border-radius: 9px; }
.task-title { color: #f5f7fa; font-size: 15px; font-weight: 600; }
.badge { padding: 0; font-size: 12px; font-weight: 700; }
.priority-high { background: transparent; color: #fb7185; }
.priority-medium { background: transparent; color: #fbbf24; }
.priority-low { background: transparent; color: #60a5fa; }
.overdue { color: #fb7185; font-weight: 700; }
.due-soon { color: #fbbf24; font-weight: 600; }
entry, textview { background: #242833; color: #f5f7fa; caret-color: #f5f7fa; }
.description-box { background: #242833; border: 1px solid rgba(255,255,255,.10); border-radius: 10px; padding: 8px; }
.tabs { background: transparent; padding: 0; }
.action-button { min-width: 22px; min-height: 24px; border-radius: 7px; padding: 2px; background: transparent; border: none; box-shadow: none; }
.action-button:hover { background: rgba(255,255,255,.07); }
.action-complete { color: #4ade80; }
.action-cancel { color: #fb7185; }
.action-delete { color: #9ca3af; }
.status-completed { color: #4ade80; font-weight: 700; }
.status-cancelled { color: #fb7185; font-weight: 700; }
.drag-handle { color: #6b7280; font-size: 18px; margin-right: 8px; }
.detail-description { background: transparent; color: #d1d5db; }
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
def action_button(label,tip,css,callback):
 b=Gtk.Button(label=label,tooltip_text=tip,css_classes=["action-button",css]);b.connect("clicked",callback);return b
def action_icon_button(icon,tip,css,callback):
 b=Gtk.Button(icon_name=icon,tooltip_text=tip,css_classes=["action-button",css]);b.connect("clicked",callback);return b

class Window(Adw.ApplicationWindow):
 def __init__(self,app,title):
  super().__init__(application=app,title=title,default_width=520,default_height=620,resizable=False)
  view=Adw.ToolbarView(); header=Adw.HeaderBar();header.set_decoration_layout(":close");header.set_title_widget(Gtk.Label(label=title,css_classes=["title"])); view.add_top_bar(header)
  self.box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=14,css_classes=["panel"]); self.toasts=Adw.ToastOverlay(child=self.box); view.set_content(self.toasts); self.set_content(view)
  keys=Gtk.EventControllerKey();keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE);keys.connect("key-pressed",lambda _c,key,*_: self.close() or True if key==Gdk.KEY_Escape else False); self.add_controller(keys)
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
  radio=run("nmcli","radio","wifi");enabled=radio.stdout.strip()=="enabled"
  if not enabled:return enabled,[]
  result=run("nmcli","-t","--escape","yes","-f","IN-USE,SSID,SIGNAL,SECURITY","device","wifi","list","--rescan","yes" if force else "no")
  if result.returncode:raise RuntimeError(result.stderr.strip() or "Falha ao consultar redes")
  output=result.stdout
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
  if not networks:self.status.set_text("Nenhuma rede encontrada");return False
  for net in networks:
   row=Gtk.ListBoxRow(activatable=True,css_classes=["row"]); content=Gtk.Box(spacing=12)
   signal_icon="󰤨" if net["signal"]>=70 else "󰤥" if net["signal"]>=40 else "󰤟"; content.append(Gtk.Label(label=signal_icon))
   labels=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,hexpand=True); labels.append(Gtk.Label(label=net["ssid"],xalign=0,max_width_chars=34,css_classes=["panel-primary"])); detail="Conectado" if net["active"] else f'{net["signal"]}% · {"Protegida" if net["security"] not in ("","--") else "Aberta"}'; labels.append(Gtk.Label(label=detail,xalign=0,css_classes=["connected" if net["active"] else "muted"])); content.append(labels)
   if net["security"] not in ("","--"):content.append(Gtk.Image.new_from_icon_name("system-lock-screen-symbolic"))
   content.set_cursor_from_name("pointer");click=Gtk.GestureClick();click.connect("released",lambda _gesture,_press,_x,_y,network=net:self.select(None,network));content.add_controller(click);row.set_child(content);self.list.append(row)
  return False
 def select(self,_row,net):
  if net["active"]:background(lambda:run("nmcli","connection","down","id",net["ssid"]),lambda *_:self.refresh());return
  def saved_done(result,_error):
   if result.returncode==0:self.refresh();return False
   if net["security"] in ("","--"):self.connect_network(net,None);return False
   dialog=Adw.AlertDialog(heading=f'Conectar a “{net["ssid"]}”',body="Digite a senha da rede.");content=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,width_request=430,margin_top=10,margin_bottom=8,margin_start=8,margin_end=8);password=Gtk.PasswordEntry(show_peek_icon=True,activates_default=True,placeholder_text="Senha");content.append(password);dialog.set_extra_child(content);dialog.add_response("cancel","Cancelar");dialog.add_response("connect","Conectar");dialog.set_response_appearance("connect",Adw.ResponseAppearance.SUGGESTED);dialog.set_default_response("connect");dialog.set_close_response("cancel");dialog.connect("response",lambda _d,r:self.connect_network(net,password.get_text()) if r=="connect" else None);dialog.present(self);GLib.idle_add(lambda:(password.grab_focus(),False)[1]);return False
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
  tabs=Gtk.Box(homogeneous=True,spacing=8,css_classes=["tabs"]);self.open_tab=Gtk.ToggleButton(label="●  Open",active=True);self.closed_tab=Gtk.ToggleButton(label="✓  Closed",group=self.open_tab);self.open_tab.connect("toggled",lambda b:self.change_view("open") if b.get_active() else None);self.closed_tab.connect("toggled",lambda b:self.change_view("closed") if b.get_active() else None);tabs.append(self.open_tab);tabs.append(self.closed_tab);self.box.append(tabs)
  self.view_status="open";self.counter=Gtk.Label(xalign=0,css_classes=["subtitle"]);self.box.append(self.counter)
  self.list=Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE,css_classes=["card"]);self.empty=Gtk.Label(justify=Gtk.Justification.CENTER,css_classes=["subtitle"]);self.content_stack=Gtk.Stack(vexpand=True);self.content_stack.add_named(Gtk.ScrolledWindow(vexpand=True,hscrollbar_policy=Gtk.PolicyType.NEVER,child=self.list),"list");self.content_stack.add_named(self.empty,"empty");self.box.append(self.content_stack);self.reload()
  shortcuts=Gtk.EventControllerKey();shortcuts.connect("key-pressed",lambda _c,key,_code,state:(self.task_form() or True) if key==Gdk.KEY_n and state&Gdk.ModifierType.CONTROL_MASK else False);self.add_controller(shortcuts)
 def migrate(self):
  if self.path.exists():return
  old=[x.strip() for x in self.legacy.read_text().splitlines() if x.strip()] if self.legacy.exists() else []
  created=datetime.now().isoformat(timespec="seconds")
  self.path.write_text(json.dumps([{"id":str(uuid.uuid4()),"title":x,"created_at":created,"due_date":None,"priority":"medium"} for x in old],ensure_ascii=False,indent=2))
 def tasks(self):
  try:tasks=json.loads(self.path.read_text())
  except (json.JSONDecodeError,OSError):return []
  for index,task in enumerate(tasks):task.setdefault("status","open");task.setdefault("order",index);task.setdefault("description","");task.setdefault("closed_at",None);task.setdefault("cancel_reason","")
  return tasks
 def save(self,tasks):
  temp=self.path.with_suffix(".tmp");temp.write_text(json.dumps(tasks,ensure_ascii=False,indent=2));temp.replace(self.path);subprocess.run(["pkill","-RTMIN+8","waybar"],capture_output=True);self.reload()
 def change_view(self,status):self.view_status=status;self.reload()
 def reload(self):
  while child:=self.list.get_first_child():self.list.remove(child)
  all_tasks=self.tasks();open_count=sum(x["status"]=="open" for x in all_tasks);closed_count=len(all_tasks)-open_count;self.open_tab.set_label(f"●  Open  {open_count}");self.closed_tab.set_label(f"✓  Closed  {closed_count}")
  tasks=sorted((x for x in all_tasks if (x["status"]=="open")== (self.view_status=="open")),key=lambda x:x.get("order",0) if self.view_status=="open" else x.get("closed_at","") ,reverse=self.view_status=="closed")
  overdue=sum(bool(x.get("due_date") and x["due_date"]<date.today().isoformat()) for x in tasks if x["status"]=="open");n=len(tasks);self.counter.set_text((f"{n} aberta{'s' if n!=1 else ''}"+(f" · {overdue} vencida{'s' if overdue!=1 else ''}" if overdue else "")) if self.view_status=="open" else f"{n} fechada{'s' if n!=1 else ''}")
  if not tasks:self.empty.set_label("Tudo em dia!\nCrie uma tarefa para começar." if self.view_status=="open" else "Nenhuma tarefa fechada.");self.content_stack.set_visible_child_name("empty");return
  self.content_stack.set_visible_child_name("list")
  for task in tasks:self.list.append(self.task_row(task))
 def task_row(self,task):
  row=Gtk.ListBoxRow(activatable=True);content=Gtk.Box(spacing=10,css_classes=["row"])
  handle=None
  if task["status"]=="open":handle=Gtk.Label(label="⋮⋮",tooltip_text="Arraste para reordenar",css_classes=["drag-handle"]);content.append(handle)
  else:content.append(Gtk.Label(label="✓" if task["status"]=="completed" else "●",css_classes=["status-completed" if task["status"]=="completed" else "status-cancelled"]))
  body=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=3,hexpand=True);body.append(Gtk.Label(label=task["title"],xalign=0,hexpand=True,wrap=True,css_classes=["task-title"]));priority=task.get("priority","medium");priority_label={"high":"Alta","medium":"Média","low":"Baixa"}[priority]
  description=task.get("description","").strip()
  if description:
   preview=description.replace("\n"," ");preview=preview[:105].rstrip()+("…" if len(preview)>105 else "");body.append(Gtk.Label(label=preview,xalign=0,wrap=False,css_classes=["muted"]))
  created=datetime.fromisoformat(task["created_at"]).strftime("Criada em %d/%m/%Y") if task.get("created_at") else "Data de criação desconhecida";due=task.get("due_date")
  if due:
   due_date=date.fromisoformat(due);delta=(due_date-date.today()).days
   if delta<0:deadline=f"Vencida há {abs(delta)} dia{'s' if abs(delta)!=1 else ''}";css="overdue"
   elif delta==0:deadline="Vence hoje";css="due-soon"
   elif delta==1:deadline="Vence amanhã";css="due-soon"
   else:deadline=f"Prazo: {due_date.strftime('%d/%m/%Y')}";css="muted"
   meta=Gtk.Box(spacing=8);meta.append(Gtk.Label(label=f"● {priority_label}",css_classes=["badge",f"priority-{priority}"]));meta.append(Gtk.Label(label=created,xalign=0,css_classes=["muted"]));meta.append(Gtk.Label(label="•"));meta.append(Gtk.Label(label=deadline,xalign=0,css_classes=[css]));body.append(meta)
  else:
   meta=Gtk.Box(spacing=8);meta.append(Gtk.Label(label=f"● {priority_label}",css_classes=["badge",f"priority-{priority}"]));meta.append(Gtk.Label(label=f"{created}  •  Sem prazo",xalign=0,css_classes=["muted"]));body.append(meta)
  if task["status"]!="open":
   closed=datetime.fromisoformat(task["closed_at"]).strftime("%d/%m/%Y às %H:%M") if task.get("closed_at") else "data desconhecida";status_text=(f"Concluída em {closed}" if task["status"]=="completed" else f"Cancelada em {closed}");body.append(Gtk.Label(label=status_text,xalign=0,css_classes=["status-completed" if task["status"]=="completed" else "status-cancelled"]))
  content.append(body);body.set_cursor_from_name("pointer");click=Gtk.GestureClick();click.connect("released",lambda *_:self.task_details(task));body.add_controller(click)
  if task["status"]=="open":
   actions=Gtk.Box(spacing=1);actions.append(action_icon_button("object-select-symbolic","Concluir","action-complete",lambda *_:self.set_status(task["id"],"completed")));actions.append(action_icon_button("window-close-symbolic","Cancelar","action-cancel",lambda *_:self.cancel_task(task)));actions.append(action_icon_button("user-trash-symbolic","Excluir","action-delete",lambda *_:self.confirm_delete(task)));content.append(actions)
   source=Gtk.DragSource(actions=Gdk.DragAction.MOVE);source.connect("prepare",lambda *_:Gdk.ContentProvider.new_for_value(task["id"]));handle.add_controller(source)
   target=Gtk.DropTarget.new(str,Gdk.DragAction.MOVE);target.connect("drop",lambda _t,value,_x,_y:self.reorder(value,task["id"]));row.add_controller(target)
  else:content.append(action_icon_button("user-trash-symbolic","Excluir","action-delete",lambda *_:self.confirm_delete(task)))
  row.set_child(content);return row
 def set_status(self,task_id,status,reason=""):
  tasks=self.tasks()
  for task in tasks:
   if task["id"]==task_id:task.update(status=status,closed_at=datetime.now().isoformat(timespec="seconds"),cancel_reason=reason)
  self.save(tasks)
 def reorder(self,source_id,target_id):
  if source_id==target_id:return False
  tasks=self.tasks();opened=sorted([x for x in tasks if x["status"]=="open"],key=lambda x:x["order"]);source=next((x for x in opened if x["id"]==source_id),None);target=next((x for x in opened if x["id"]==target_id),None)
  if not source or not target:return False
  source_index=opened.index(source);target_index=opened.index(target);opened.remove(source);new_target=opened.index(target);opened.insert(new_target+1 if source_index<target_index else new_target,source)
  for index,task in enumerate(opened):task["order"]=index
  self.save(tasks);return True
 def confirm_delete(self,task):
  dialog=Adw.AlertDialog(heading="Excluir permanentemente?",body=task["title"]);dialog.add_response("back","Voltar");dialog.add_response("delete","Excluir");dialog.set_response_appearance("delete",Adw.ResponseAppearance.DESTRUCTIVE);dialog.set_close_response("back");dialog.connect("response",lambda _d,r:self.delete_task(task["id"]) if r=="delete" else None);dialog.present(self)
 def delete_task(self,task_id):self.save([task for task in self.tasks() if task["id"]!=task_id])
 def cancel_task(self,task):
  dialog=Adw.AlertDialog(heading="Cancelar tarefa?",body="Você pode registrar uma justificativa ou deixar em branco.");content=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,width_request=480,margin_top=10,margin_bottom=8,margin_start=8,margin_end=8);reason=Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR,height_request=110,css_classes=["description-box"]);content.append(reason);dialog.set_extra_child(content);dialog.add_response("back","Voltar");dialog.add_response("cancel","Cancelar tarefa");dialog.set_response_appearance("cancel",Adw.ResponseAppearance.DESTRUCTIVE);dialog.set_close_response("back")
  def response(_dialog,action):
   buffer=reason.get_buffer();text=buffer.get_text(buffer.get_start_iter(),buffer.get_end_iter(),False).strip()
   if action=="cancel":self.set_status(task["id"],"cancelled",text)
  dialog.connect("response",response);keys=Gtk.EventControllerKey()
  def key_pressed(_controller,key,_code,state):
   if key in (Gdk.KEY_Return,Gdk.KEY_KP_Enter) and not state&Gdk.ModifierType.SHIFT_MASK:dialog.emit("response","cancel");dialog.close();return True
   return False
  keys.connect("key-pressed",key_pressed);reason.add_controller(keys);dialog.present(self);GLib.idle_add(lambda:(reason.grab_focus(),False)[1])
 def task_details(self,task):
  dialog=Adw.AlertDialog(heading=task["title"]);details=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=10,width_request=500,margin_top=8,margin_bottom=8,margin_start=8,margin_end=8)
  if task.get("description"):details.append(Gtk.Label(label=task["description"],xalign=0,wrap=True,selectable=False,css_classes=["detail-description"]))
  priority_label={"low":"Baixa","medium":"Média","high":"Alta"}.get(task.get("priority"),"Baixa");created_label=datetime.fromisoformat(task["created_at"]).strftime("%d/%m/%Y");details.append(Gtk.Label(label=f"Prioridade: {priority_label}  •  Criada em {created_label}",xalign=0,css_classes=["muted"]));dialog.set_extra_child(details);dialog.add_response("close","Fechar");dialog.add_response("edit","Editar");dialog.set_response_appearance("edit",Adw.ResponseAppearance.SUGGESTED);dialog.set_close_response("close")
  def response(_d,action):
   if action=="edit":self.task_form(task)
  dialog.connect("response",response);dialog.present(self)
 def task_form(self,task=None):
  editing=task is not None;dialog=Adw.AlertDialog(heading="Editar tarefa" if editing else "Nova tarefa",body="Defina o que importa e quando precisa estar pronto.")
  form=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=10,width_request=520,margin_top=10,margin_bottom=6,margin_start=6,margin_end=6)
  title=Gtk.Entry(placeholder_text="Título da tarefa",text=task["title"] if editing else "",activates_default=True);form.append(title)
  form.append(Gtk.Label(label="Descrição (opcional)",xalign=0,css_classes=["panel-primary"]))
  description=Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR,height_request=72,css_classes=["description-box"]);description.get_buffer().set_text(task.get("description","") if editing else "");form.append(description)
  priority_row=Gtk.Box(spacing=10);priority_row.append(Gtk.Label(label="Prioridade",xalign=0,hexpand=True,css_classes=["panel-primary"]));priority=Gtk.DropDown.new_from_strings(self.PRIORITIES);priority.set_selected(self.PRIORITY_KEYS.index(task.get("priority","low")) if editing else 0);priority_row.append(priority);form.append(priority_row)
  has_due=Gtk.CheckButton(label="Definir prazo",active=bool(task and task.get("due_date")));form.append(has_due);calendar=Gtk.Calendar(visible=has_due.get_active());form.append(calendar);has_due.connect("toggled",lambda b:calendar.set_visible(b.get_active()))
  if editing and task.get("due_date"):
   selected=date.fromisoformat(task["due_date"]);calendar.select_day(GLib.DateTime.new_local(selected.year,selected.month,selected.day,0,0,0))
  dialog.set_extra_child(form);dialog.add_response("cancel","Cancelar");dialog.add_response("save","Salvar");dialog.set_response_appearance("save",Adw.ResponseAppearance.SUGGESTED);dialog.set_default_response("save");dialog.set_close_response("cancel")
  def response(_dialog,action):
   value=re.sub(r"\s+"," ",title.get_text()).strip()
   if action!="save":return
   if not value:self.toast("Digite um título para a tarefa.");return
   buffer=description.get_buffer();details=buffer.get_text(buffer.get_start_iter(),buffer.get_end_iter(),False).strip();selected=calendar.get_date();due=f"{selected.get_year():04d}-{selected.get_month():02d}-{selected.get_day_of_month():02d}" if has_due.get_active() else None;tasks=self.tasks()
   if editing:
    for current in tasks:
     if current["id"]==task["id"]:current.update(title=value,description=details,priority=self.PRIORITY_KEYS[priority.get_selected()],due_date=due)
   else:tasks.append({"id":str(uuid.uuid4()),"title":value,"description":details,"created_at":datetime.now().isoformat(timespec="seconds"),"due_date":due,"priority":self.PRIORITY_KEYS[priority.get_selected()],"status":"open","order":sum(x.get("status","open")=="open" for x in tasks),"closed_at":None,"cancel_reason":""})
   self.save(tasks)
  dialog.connect("response",response);description_keys=Gtk.EventControllerKey()
  def description_key(_controller,key,_code,state):
   if key in (Gdk.KEY_Return,Gdk.KEY_KP_Enter) and not state&Gdk.ModifierType.SHIFT_MASK:dialog.emit("response","save");dialog.close();return True
   return False
  description_keys.connect("key-pressed",description_key);description.add_controller(description_keys);dialog.present(self);GLib.idle_add(lambda:(title.grab_focus(),False)[1])

class App(Adw.Application):
 def __init__(self,mode):super().__init__(application_id=f"com.leonardoernica.Waybar.{mode.title()}",flags=Gio.ApplicationFlags.DEFAULT_FLAGS);self.mode=mode;self.window=None
 def do_startup(self):
  Adw.Application.do_startup(self);Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.FORCE_DARK)
 def do_activate(self):
  if not self.window:self.window=Wifi(self) if self.mode=="wifi" else Todo(self);self.window.connect("close-request",lambda *_:self.quit() or False)
  self.window.present()
def main():
 mode=sys.argv[1] if len(sys.argv)>1 else ""
 if mode not in ("wifi","todo"):return 2
 provider=Gtk.CssProvider();provider.load_from_data(CSS);Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(),provider,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION);return App(mode).run([sys.argv[0]])
if __name__=="__main__":raise SystemExit(main())
