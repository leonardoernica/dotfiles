"""SUPER+D palette: apps, calculator, semantic file search and code search in one resident window."""
import ast, hashlib, json, math, operator, os, re, subprocess, threading, time
from pathlib import Path
import gi
gi.require_version("Gtk", "4.0"); gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk, Pango
import config, readers, search
from embed import Embedder
from store import Store

CSS = b"""
window.garimpo { background: transparent; }
.shell { background: rgba(22,23,27,.975); color: #f3f4f6; border: 1px solid rgba(255,255,255,.08); border-radius: 18px; }
.top { padding: 16px 20px 14px; }
.top image { color: #a1a1aa; }
entry.query, entry.query:focus-within { background: none; border: none; box-shadow: none; outline: none; font-size: 21px; color: #f3f4f6; min-height: 34px; padding: 0; }
.scope { background: rgba(168,199,250,.14); color: #a8c7fa; border-radius: 999px; padding: 2px 10px; font-size: 12px; font-weight: 700; }
.divider { background: rgba(255,255,255,.07); min-height: 1px; }
list.results { background: transparent; padding: 8px; }
list.results row { border-radius: 11px; padding: 7px 10px; margin: 1px 0; background: transparent; }
list.results row:selected { background: #2c2e34; }
list.results row.section { padding: 10px 10px 3px; }
.section-label { color: #71717a; font-size: 11px; font-weight: 700; letter-spacing: 1px; }
.title { font-size: 14px; font-weight: 600; }
.subtitle { color: #a1a1aa; font-size: 12px; }
.snippet { color: #8b8b94; font-size: 12px; }
.thumb { border-radius: 7px; background: rgba(255,255,255,.04); }
.badge { color: #71717a; font-size: 11px; }
.calc { font-size: 22px; font-weight: 700; color: #a8c7fa; }
.preview { background: rgba(255,255,255,.025); border-left: 1px solid rgba(255,255,255,.06); padding: 16px; }
.preview-pic { border-radius: 10px; background: rgba(0,0,0,.25); }
.preview-title { font-size: 15px; font-weight: 700; }
.preview-text { color: #c4c4cc; font-size: 12.5px; }
.footer { padding: 9px 18px; color: #71717a; font-size: 11.5px; }
.empty { color: #71717a; padding: 28px; }
.tip { color: #8b8b94; font-size: 13px; }
.tip-key { color: #a8c7fa; font-size: 13px; }
"""

KIND_ICON = {"pdf": "application-pdf", "image": "image-x-generic", "video": "video-x-generic", "audio": "audio-x-generic",
             "text": "text-x-generic", "office": "x-office-document", "code": "text-x-script", "other": "text-x-generic"}
KIND_LABEL = {"pdf": "PDF", "image": "Imagem", "video": "Vídeo", "audio": "Áudio", "text": "Texto", "office": "Documento",
              "code": "Código", "other": "Arquivo"}
BROWSERS = ("chrome", "chromium", "brave", "firefox", "vivaldi", "edge", "zen")

def esc(text): return GLib.markup_escape_text(text or "")

def highlight(text, query):
 """Escape text and bold the query words (accent-insensitive)."""
 index, folded = [], []
 for i, ch in enumerate(text):
  f = search.fold(ch); folded.append(f); index += [i] * len(f)
 folded, spans = "".join(folded), []
 for w in set(search.words(query)):
  if len(w) < 3 and not w.isdigit(): continue  # "de", "em": noise when highlighted
  spans += [(index[m.start()], index[m.end() - 1] + 1) for m in re.finditer(r"(?<!\w)" + re.escape(w), folded)]
 out, last = [], 0
 for a, b in sorted(spans):
  if a < last: continue
  out += [esc(text[last:a]), "<span foreground=\"#a8c7fa\" weight=\"bold\">", esc(text[a:b]), "</span>"]; last = b
 return "".join(out + [esc(text[last:])])

# ── calculator ─────────────────────────────────────────────────────────────
OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
       ast.Pow: operator.pow, ast.Mod: operator.mod, ast.FloorDiv: operator.floordiv, ast.USub: operator.neg, ast.UAdd: operator.pos}
FUNCS = {"sqrt": math.sqrt, "sin": math.sin, "cos": math.cos, "tan": math.tan, "log": math.log10, "ln": math.log, "abs": abs, "round": round}
CONSTS = {"pi": math.pi, "e": math.e}

def calculate(query):
 expr = query.strip().lstrip("=").replace("^", "**").replace("×", "*").replace("÷", "/")
 expr = re.sub(r"(\d),(\d)", r"\1.\2", expr)
 if not re.search(r"\d", expr) or not re.fullmatch(r"[\d\s.+\-*/%()a-z*]+", expr) or not re.search(r"[-+*/%(]|sqrt|log|ln|sin|cos|tan", expr): return None
 def ev(node):
  if isinstance(node, ast.Expression): return ev(node.body)
  if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)): return node.value
  if isinstance(node, ast.BinOp) and type(node.op) in OPS:
   left, right = ev(node.left), ev(node.right)
   if isinstance(node.op, ast.Pow) and abs(right) > 1000: raise ValueError
   return OPS[type(node.op)](left, right)
  if isinstance(node, ast.UnaryOp) and type(node.op) in OPS: return OPS[type(node.op)](ev(node.operand))
  if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in FUNCS and len(node.args) == 1: return FUNCS[node.func.id](ev(node.args[0]))
  if isinstance(node, ast.Name) and node.id in CONSTS: return CONSTS[node.id]
  raise ValueError
 try: value = ev(ast.parse(expr, mode="eval"))
 except (SyntaxError, ValueError, TypeError, ZeroDivisionError, OverflowError): return None
 if isinstance(value, float) and not math.isfinite(value): return None
 text = f"{value:,.10g}" if isinstance(value, float) else f"{value:,}"
 return text.replace(",", "\0").replace(".", ",").replace("\0", ".")

# ── apps and usage ─────────────────────────────────────────────────────────
class Usage:
 def __init__(self):
  self.path = config.STATE / "usage.json"
  try: self.data = json.loads(self.path.read_text())
  except (OSError, ValueError): self.data = {}
 def bump(self, kind, key):
  entry = self.data.setdefault(kind, {}).setdefault(key, [0, 0]); entry[0] += 1; entry[1] = time.time()
  try: self.path.parent.mkdir(parents=True, exist_ok=True); self.path.write_text(json.dumps(self.data))
  except OSError: pass
 def boost(self, kind, key):
  count, last = self.data.get(kind, {}).get(key, (0, 0))
  return 0.06 * math.log1p(count) * (1.0 if time.time() - last < 14 * 86400 else 0.5)
 def recent(self, kind, n):
  items = sorted(self.data.get(kind, {}).items(), key=lambda kv: -kv[1][1])
  return [k for k, _ in items[:n]]

def app_score(app, query):
 q = search.fold(query)
 name = search.fold(app.get_display_name() or "")
 if name.startswith(q): return 1.0
 if any(w.startswith(q) for w in name.split()): return 0.85
 if q in name: return 0.7
 extra = search.fold(" ".join(filter(None, [app.get_generic_name() if hasattr(app, "get_generic_name") else "", app.get_executable() or "",
                                           " ".join(app.get_keywords() if hasattr(app, "get_keywords") else [])])))
 if len(q) >= 3 and q in extra: return 0.55
 it = iter(name)
 return 0.4 if len(q) >= 3 and all(ch in it for ch in q) else 0.0

# ── the window ─────────────────────────────────────────────────────────────
class Palette(Gtk.ApplicationWindow):
 def __init__(self, app):
  super().__init__(application=app, title="Garimpo", decorated=False, resizable=False, default_width=800, default_height=560)
  self.add_css_class("garimpo"); self.app = app; self.cfg = app.cfg
  self.query, self.items, self.preview_on, self.thumbs = "", [], False, {}
  shell = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, css_classes=["shell"]); self.set_child(shell)
  top = Gtk.Box(spacing=12, css_classes=["top"])
  top.append(Gtk.Image(icon_name="system-search-symbolic", pixel_size=20))
  self.entry = Gtk.Entry(hexpand=True, placeholder_text="Descreva o que procura… apps, arquivos, imagens, vídeos, code:", css_classes=["query"])
  self.entry.connect("changed", self.on_changed); self.entry.connect("activate", lambda *_: self.open_selected())
  top.append(self.entry)
  self.scope_chip = Gtk.Label(label="CÓDIGO", css_classes=["scope"], visible=False); top.append(self.scope_chip)
  self.spinner = Gtk.Spinner(); top.append(self.spinner)
  shell.append(top); shell.append(Gtk.Box(css_classes=["divider"]))
  body = Gtk.Box(vexpand=True)
  self.list = Gtk.ListBox(css_classes=["results"], selection_mode=Gtk.SelectionMode.SINGLE, activate_on_single_click=True)
  self.list.connect("row-activated", lambda _l, row: self.open_item(row.item))
  self.list.connect("row-selected", lambda *_: self.update_preview())
  self.scroll = Gtk.ScrolledWindow(child=self.list, hexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER, width_request=470)
  body.append(self.scroll)
  self.preview = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, css_classes=["preview"], width_request=300, hexpand=False)
  self.preview_pic = Gtk.Picture(content_fit=Gtk.ContentFit.CONTAIN, height_request=200, css_classes=["preview-pic"], can_shrink=True)
  self.preview_title = Gtk.Label(xalign=0, wrap=True, wrap_mode=Pango.WrapMode.WORD_CHAR, css_classes=["preview-title"])
  self.preview_meta = Gtk.Label(xalign=0, wrap=True, wrap_mode=Pango.WrapMode.WORD_CHAR, css_classes=["subtitle"])
  self.preview_text = Gtk.Label(xalign=0, yalign=0, wrap=True, wrap_mode=Pango.WrapMode.WORD_CHAR, css_classes=["preview-text"], vexpand=True)
  for w in (self.preview_pic, self.preview_title, self.preview_meta, Gtk.ScrolledWindow(child=self.preview_text, vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)): self.preview.append(w)
  self.revealer = Gtk.Revealer(child=self.preview, transition_type=Gtk.RevealerTransitionType.SLIDE_LEFT, transition_duration=140)
  body.append(self.revealer); shell.append(body); shell.append(Gtk.Box(css_classes=["divider"]))
  foot = Gtk.Box(css_classes=["footer"], spacing=12)
  hints = "<b>↵</b> abrir   <b>Ctrl+↵</b> mostrar na pasta   <b>Ctrl+C</b> copiar   <b>Tab</b> prévia   <b>Esc</b> fechar"
  foot.append(Gtk.Label(use_markup=True, label=hints, xalign=0, hexpand=True))
  self.status = Gtk.Label(xalign=1, ellipsize=Pango.EllipsizeMode.MIDDLE, max_width_chars=42); foot.append(self.status)
  shell.append(foot)
  keys = Gtk.EventControllerKey(propagation_phase=Gtk.PropagationPhase.CAPTURE); keys.connect("key-pressed", self.on_key); self.add_controller(keys)
  self.connect("notify::is-active", self.on_active)
  self.connect("close-request", lambda *_: self.dismiss() or True)

 # visibility
 def summon(self):
  self.entry.set_text(""); self.render_empty(); self.present(); self.entry.grab_focus()
  self.refresh_status(); self.app.worker.warm()
  if not getattr(self, "status_timer", None): self.status_timer = GLib.timeout_add_seconds(2, self.refresh_status)
 def dismiss(self):
  self.set_visible(False)
  if getattr(self, "status_timer", None): GLib.source_remove(self.status_timer); self.status_timer = None
 def on_active(self, *_):
  if not self.is_active() and self.get_visible(): GLib.timeout_add(120, self.dismiss_if_inactive)
 def dismiss_if_inactive(self):
  if not self.is_active() and self.get_visible(): self.dismiss()
  return False

 def refresh_status(self):
  st = self.app.index_status()
  self.status.set_markup(esc(st)); return True

 # keyboard
 def on_key(self, _ctrl, key, _code, mods):
  ctrl = bool(mods & Gdk.ModifierType.CONTROL_MASK)
  if key == Gdk.KEY_Escape:
   if self.preview_on: self.toggle_preview()
   elif self.entry.get_text(): self.entry.set_text("")
   else: self.dismiss()
   return True
  if key in (Gdk.KEY_Down, Gdk.KEY_KP_Down) or (ctrl and key in (Gdk.KEY_n, Gdk.KEY_j)): self.move(1); return True
  if key in (Gdk.KEY_Up, Gdk.KEY_KP_Up) or (ctrl and key in (Gdk.KEY_p, Gdk.KEY_k)): self.move(-1); return True
  if key == Gdk.KEY_Page_Down: self.move(6); return True
  if key == Gdk.KEY_Page_Up: self.move(-6); return True
  if key in (Gdk.KEY_Return, Gdk.KEY_KP_Enter): self.open_selected(reveal=ctrl); return True
  if key in (Gdk.KEY_Tab, Gdk.KEY_ISO_Left_Tab): self.toggle_preview(); return True
  if ctrl and key in (Gdk.KEY_c, Gdk.KEY_C) and not self.entry.get_selection_bounds(): self.copy_selected(); return True
  return False

 def selectable_rows(self):
  rows, row = [], self.list.get_first_child()
  while row:
   if isinstance(row, Gtk.ListBoxRow) and row.get_selectable(): rows.append(row)
   row = row.get_next_sibling()
  return rows

 def move(self, delta):
  rows = self.selectable_rows()
  if not rows: return
  cur = self.list.get_selected_row()
  i = rows.index(cur) + delta if cur in rows else 0
  self.select(rows[max(0, min(len(rows) - 1, i))])

 def select(self, row):
  self.list.select_row(row)
  ok, bounds = row.compute_bounds(self.list)
  if ok:
   adj = self.scroll.get_vadjustment(); y, h = bounds.get_y(), bounds.get_height()
   if y < adj.get_value(): adj.set_value(y - 8)
   elif y + h > adj.get_value() + adj.get_page_size(): adj.set_value(y + h - adj.get_page_size() + 8)

 # searching
 def on_changed(self, entry):
  self.query = entry.get_text()
  scope, text = search.parse(self.query)
  self.scope_chip.set_visible(scope == "code")
  if not self.query.strip(): self.render_empty(); return
  self.fast_items = self.quick_items(self.query, scope, text)
  self.render(self.fast_items, [])
  self.spinner.start()
  self.app.worker.submit(self.query, self.on_results)

 def quick_items(self, query, scope, text):
  items = []
  value = calculate(query)
  if value is not None: items.append(dict(type="calc", value=value, expr=query.strip()))
  if scope == "files" and len(text) >= 1:
   scored = sorted(((app_score(a, text) + self.app.usage.boost("apps", a.get_id() or ""), a) for a in self.app.apps()), key=lambda s: -s[0])
   items += [dict(type="app", app=a) for s, a in scored[:5] if s >= 0.4]
  return items

 def on_results(self, query, results, final):
  if query != self.query: return
  if final: self.spinner.stop()
  scope, text = search.parse(query)
  items = []
  for r in results:
   r["score"] += self.app.usage.boost("files", r["path"])
  for r in sorted(results, key=lambda r: -r["score"]): items.append(dict(r, type="file", scope=scope))
  if final and scope == "files": items.append(dict(type="web", text=text))
  self.render(self.fast_items, items)

 def render_empty(self):
  self.fast_items = []
  recent_apps = [a for a in (self.app.app_by_id(i) for i in self.app.usage.recent("apps", 5)) if a]
  recent_files = [p for p in self.app.usage.recent("files", 6) if os.path.exists(p)]
  files = [dict(type="file", path=p, kind=readers.kind(Path(p)), loc=None, snippet="", text="", scope="files") for p in recent_files]
  self.render([dict(type="app", app=a) for a in recent_apps], files, empty=True)

 def render(self, quick, files, empty=False):
  while child := self.list.get_first_child(): self.list.remove(child)
  self.items = []
  apps = [i for i in quick if i["type"] == "app"]; calc = [i for i in quick if i["type"] == "calc"]
  media = [i for i in files if i["type"] == "file" and i.get("media")]
  file_items = [i for i in files if i["type"] == "file" and not i.get("media")]; web = [i for i in files if i["type"] == "web"]
  if (file_items or media) and len(apps) > 3: apps = apps[:3]
  scope = search.parse(self.query)[0]
  groups = [("CALCULADORA", calc), ("RECENTES" if empty else "APLICATIVOS", apps), ("IMAGENS, VÍDEOS E ÁUDIO", media),
            ("ARQUIVOS RECENTES" if empty else ("CÓDIGO" if scope == "code" else "ARQUIVOS"), file_items), ("WEB", web)]
  for title, group in groups:
   if not group: continue
   header = Gtk.ListBoxRow(selectable=False, activatable=False, css_classes=["section"])
   header.set_child(Gtk.Label(label=title, xalign=0, css_classes=["section-label"])); self.list.append(header)
   for item in group: self.list.append(self.make_row(item))
  rows = self.selectable_rows()
  if empty and not rows: self.list.append(self.tips_row())
  if rows: self.list.select_row(rows[0]); self.scroll.get_vadjustment().set_value(0)
  elif self.query.strip() and not self.spinner.get_spinning():
   empty_row = Gtk.ListBoxRow(selectable=False, activatable=False)
   empty_row.set_child(Gtk.Label(label="Nada encontrado. Tente descrever com outras palavras.", css_classes=["empty"])); self.list.append(empty_row)
  self.update_preview()

 def tips_row(self):
  row = Gtk.ListBoxRow(selectable=False, activatable=False)
  grid = Gtk.Grid(column_spacing=18, row_spacing=10, margin_top=26, margin_start=24)
  tips = [("um cachorro na praia", "fotos e frames de vídeo pelo que mostram"),
          ("cláusula sobre animais no contrato", "a página exata do PDF"),
          ("erro de pagamento recusado", "capturas de tela pelo texto"),
          ("code: retry com backoff", "código nas pastas que você habilitar"),
          ("(1200*12)/7", "calculadora · Enter copia")]
  for i, (example, what) in enumerate(tips):
   grid.attach(Gtk.Label(label=example, xalign=0, css_classes=["tip-key"]), 0, i, 1, 1)
   grid.attach(Gtk.Label(label=what, xalign=0, css_classes=["tip"]), 1, i, 1, 1)
  row.set_child(grid); return row

 def make_row(self, item):
  row = Gtk.ListBoxRow(); row.item = item
  box = Gtk.Box(spacing=12); row.set_child(box)
  text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True, valign=Gtk.Align.CENTER, spacing=1)
  t = item["type"]
  if t == "app":
   app = item["app"]
   box.append(Gtk.Image(gicon=app.get_icon() or Gio.ThemedIcon.new("application-x-executable"), pixel_size=32))
   text.append(Gtk.Label(label=app.get_display_name(), xalign=0, css_classes=["title"], ellipsize=Pango.EllipsizeMode.END))
   desc = app.get_description() or (app.get_generic_name() if hasattr(app, "get_generic_name") else "") or ""
   if desc: text.append(Gtk.Label(label=desc, xalign=0, css_classes=["subtitle"], ellipsize=Pango.EllipsizeMode.END))
   badge = "Aplicativo"
  elif t == "calc":
   box.append(Gtk.Image(icon_name="accessories-calculator", pixel_size=32))
   text.append(Gtk.Label(label=f"= {item['value']}", xalign=0, css_classes=["calc"], selectable=False))
   text.append(Gtk.Label(label="Enter copia o resultado", xalign=0, css_classes=["subtitle"]))
   badge = ""
  elif t == "web":
   browser = Gio.AppInfo.get_default_for_uri_scheme("https")
   box.append(Gtk.Image(gicon=(browser and browser.get_icon()) or Gio.ThemedIcon.new("web-browser-symbolic"), pixel_size=32))
   text.append(Gtk.Label(label=f"Pesquisar na web por “{item['text']}”", xalign=0, css_classes=["title"], ellipsize=Pango.EllipsizeMode.END))
   badge = ""
  else:
   path = item["path"]
   icon = Gtk.Image(pixel_size=36, css_classes=["thumb"])
   icon.set_from_gicon(self.file_icon(path)); box.append(icon)
   if item["kind"] == "image": self.load_thumb(path, icon)
   text.append(Gtk.Label(label=os.path.basename(path), xalign=0, css_classes=["title"], ellipsize=Pango.EllipsizeMode.MIDDLE))
   where = " · ".join(filter(None, [search.location(item), search.home(os.path.dirname(path))]))
   text.append(Gtk.Label(label=where, xalign=0, css_classes=["subtitle"], ellipsize=Pango.EllipsizeMode.MIDDLE))
   if item.get("snippet"):
    text.append(Gtk.Label(use_markup=True, label=highlight(item["snippet"], search.parse(self.query)[1]), xalign=0, css_classes=["snippet"],
                          ellipsize=Pango.EllipsizeMode.END, lines=1))
   badge = KIND_LABEL.get(item["kind"], "")
  box.append(text)
  if badge: box.append(Gtk.Label(label=badge, css_classes=["badge"], valign=Gtk.Align.CENTER))
  return row

 def file_icon(self, path):
  ctype, _ = Gio.content_type_guess(path, None)
  return Gio.content_type_get_icon(ctype)

 def load_thumb(self, path, image, size=72):
  if path in self.thumbs: image.set_from_paintable(self.thumbs[path]); return
  def work():
   data = readers.image_bytes(Path(path), size)
   if data: GLib.idle_add(done, data)
  def done(data):
   try: tex = Gdk.Texture.new_from_bytes(GLib.Bytes.new(data))
   except GLib.Error: return False
   if len(self.thumbs) > 400: self.thumbs.clear()
   self.thumbs[path] = tex; image.set_from_paintable(tex); return False
  threading.Thread(target=work, daemon=True).start()

 # preview
 def toggle_preview(self):
  self.preview_on = not self.preview_on; self.revealer.set_reveal_child(self.preview_on); self.update_preview()

 def update_preview(self):
  if not self.preview_on: return
  row = self.list.get_selected_row(); item = getattr(row, "item", None)
  self.preview_pic.set_paintable(None); self.preview_pic.set_visible(False)
  if not item: self.preview_title.set_text(""); self.preview_meta.set_text(""); self.preview_text.set_text(""); return
  if item["type"] == "app":
   app = item["app"]; self.preview_title.set_text(app.get_display_name()); self.preview_meta.set_text(app.get_id() or "")
   self.preview_text.set_text(app.get_description() or ""); return
  if item["type"] != "file":
   self.preview_title.set_text(item.get("value") or item.get("text") or ""); self.preview_meta.set_text(""); self.preview_text.set_text(""); return
  path = item["path"]
  self.preview_title.set_text(os.path.basename(path))
  try: st = os.stat(path); size = GLib.format_size(st.st_size); when = time.strftime("%d/%m/%Y %H:%M", time.localtime(st.st_mtime))
  except OSError: size = when = ""
  self.preview_meta.set_text(" · ".join(filter(None, [KIND_LABEL.get(item["kind"], ""), search.location(item), size, when, search.home(os.path.dirname(path))])))
  body = item.get("text") or ""
  self.preview_text.set_markup(highlight(body[:1500], search.parse(self.query)[1]) if body and body != os.path.basename(path) else "")
  token = object(); self.preview_token = token
  def work():
   data = preview_image(item)
   if data: GLib.idle_add(done, data)
  def done(data):
   if self.preview_token is not token: return False
   try: self.preview_pic.set_paintable(Gdk.Texture.new_from_bytes(GLib.Bytes.new(data))); self.preview_pic.set_visible(True)
   except GLib.Error: pass
   return False
  threading.Thread(target=work, daemon=True).start()

 # actions
 def selected(self):
  row = self.list.get_selected_row(); return getattr(row, "item", None)

 def open_selected(self, reveal=False):
  item = self.selected()
  if item: self.open_item(item, reveal)

 def open_item(self, item, reveal=False):
  t = item["type"]
  try:
   if t == "app":
    self.app.usage.bump("apps", item["app"].get_id() or "")
    item["app"].launch([], self.get_display().get_app_launch_context())
   elif t == "calc": self.copy_text(item["value"])
   elif t == "web":
    Gio.AppInfo.launch_default_for_uri("https://www.google.com/search?q=" + GLib.Uri.escape_string(item["text"], None, False), None)
   elif reveal: reveal_file(item["path"])
   else:
    self.app.usage.bump("files", item["path"]); open_file(item, self.cfg)
  except GLib.Error as e: self.status.set_text(f"Falha ao abrir: {e.message}"); return
  self.dismiss()

 def copy_text(self, text): self.get_clipboard().set(text)

 def copy_selected(self):
  item = self.selected()
  if not item: return
  if item["type"] == "file":
   subprocess.Popen(["wl-copy", "--type", "text/uri-list"], stdin=subprocess.PIPE, start_new_session=True).communicate(
    (Gio.File.new_for_path(item["path"]).get_uri() + "\r\n").encode())
   self.status.set_text("Arquivo copiado")
  elif item["type"] == "calc": self.copy_text(item["value"]); self.status.set_text("Resultado copiado")

# ── opening files at the right place ───────────────────────────────────────
def spawn(argv): subprocess.Popen(argv, start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def open_file(item, cfg):
 path, k, loc = item["path"], item["kind"], item.get("loc")
 uri = Gio.File.new_for_path(path).get_uri()
 ctype, _ = Gio.content_type_guess(path, None)
 handler = Gio.AppInfo.get_default_for_type(ctype, False)
 hid = (handler.get_id() or "").lower() if handler else ""
 if k == "pdf" and loc and loc > 1 and any(b in hid for b in BROWSERS):
  handler.launch_uris([f"{uri}#page={loc}"], None); return
 if k == "pdf" and loc and loc > 1 and "okular" in hid: spawn(["okular", "-p", str(loc), path]); return
 if k in ("video", "audio") and loc and "mpv" in hid: spawn(["mpv", "--force-window", f"--start={loc}", path]); return
 if k in ("code", "text") and loc and loc > 1 and cfg["editor"] in ("code", "cursor", "codium", "zed") and GLib.find_program_in_path(cfg["editor"]):
  spawn([cfg["editor"], "-g", f"{path}:{loc}"] if cfg["editor"] != "zed" else ["zed", f"{path}:{loc}"]); return
 if k == "code" and GLib.find_program_in_path(cfg["editor"]): spawn([cfg["editor"], path]); return
 Gio.AppInfo.launch_default_for_uri(uri, None)

def reveal_file(path):
 """Select the file in the file manager (org.freedesktop.FileManager1, implemented by Dolphin)."""
 uri = Gio.File.new_for_path(path).get_uri()
 try:
  Gio.bus_get_sync(Gio.BusType.SESSION).call_sync("org.freedesktop.FileManager1", "/org/freedesktop/FileManager1",
   "org.freedesktop.FileManager1", "ShowItems", GLib.Variant("(ass)", ([uri], "")), None, Gio.DBusCallFlags.NONE, 3000)
 except GLib.Error: Gio.AppInfo.launch_default_for_uri(Gio.File.new_for_path(os.path.dirname(path)).get_uri(), None)

def preview_image(item):
 """JPEG bytes for the preview pane: the image, the PDF page or the video moment."""
 path, k, loc = Path(item["path"]), item["kind"], item.get("loc")
 if k == "image": return readers.image_bytes(path, 600)
 if k not in ("pdf", "video"): return None
 try: mtime = path.stat().st_mtime
 except OSError: return None
 cache = config.CACHE / "previews" / (hashlib.sha1(f"{path}|{mtime}|{loc}".encode()).hexdigest() + ".jpg")
 if cache.exists(): return cache.read_bytes()
 if k == "pdf": data = readers.run("pdftoppm", "-f", str(loc or 1), "-l", str(loc or 1), "-scale-to", "600", "-jpeg", str(path), timeout=30, binary=True)
 else: data = readers.run("ffmpeg", "-v", "error", "-ss", str(loc or 1), "-i", str(path), "-frames:v", "1", "-vf", "scale=600:-2",
                          "-f", "image2pipe", "-vcodec", "mjpeg", "-", timeout=30, binary=True)
 if data: cache.parent.mkdir(parents=True, exist_ok=True); cache.write_bytes(data)
 return data or None

# ── background search worker (one sqlite connection, latest query wins) ────
class Worker:
 def __init__(self, cfg):
  self.cfg = cfg; self.cond = threading.Condition(); self.pending = None; self.warm_flag = False
  threading.Thread(target=self.loop, daemon=True).start()

 def submit(self, query, callback):
  with self.cond: self.pending = (query, callback); self.cond.notify()
 def warm(self):
  with self.cond: self.warm_flag = True; self.cond.notify()

 def loop(self):
  self.store = Store(config.STATE / "index.db"); self.embedder = Embedder(self.cfg)
  self.searcher = search.Searcher(self.store, self.embedder, self.cfg)
  while True:
   with self.cond:
    while not self.pending and not self.warm_flag: self.cond.wait()
    job, self.pending = self.pending, None
    warm, self.warm_flag = self.warm_flag, False
   if warm and not job:
    try: self.store.matrix("files", self.cfg["model"]); self.embedder.query("warm up"); self.embedder._props()
    except Exception: pass
    continue
   query, callback = job
   time.sleep(0.06)  # let fast typists finish the word
   with self.cond:
    if self.pending: continue
   try:
    _, quick = self.searcher.search(query, semantic=False)
    GLib.idle_add(callback, query, quick, False)
    with self.cond:
     if self.pending: continue
    _, full = self.searcher.search(query)
   except Exception as e:
    full = []; print(f"[garimpo] busca falhou: {e!r}")
   GLib.idle_add(callback, query, full, True)

class App(Adw.Application):
 def __init__(self, hidden=False):
  super().__init__(application_id=config.APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
  self.start_hidden, self.window, self._apps = hidden, None, None

 def do_startup(self):
  Adw.Application.do_startup(self)
  Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.FORCE_DARK)
  css = Gtk.CssProvider(); css.load_from_data(CSS, -1)
  Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1)
  self.cfg = config.load(); self.usage = Usage(); self.worker = Worker(self.cfg)
  self.status_db = Store(config.STATE / "index.db")
  self.monitor = Gio.AppInfoMonitor.get(); self.monitor.connect("changed", lambda *_: setattr(self, "_apps", None))
  action = Gio.SimpleAction.new("search", GLib.VariantType.new("s"))
  action.connect("activate", lambda _a, text: self.open_with(text.get_string())); self.add_action(action)
  self.hold()  # stay resident so SUPER+D opens instantly

 def apps(self):
  if self._apps is None: self._apps = [a for a in Gio.AppInfo.get_all() if a.should_show()]
  return self._apps
 def app_by_id(self, app_id): return next((a for a in self.apps() if a.get_id() == app_id), None)

 def index_status(self):
  try: st = json.loads(self.status_db.get("status") or "{}")
  except Exception: st = {}
  state = st.get("state")
  if state == "indexing": return f"Indexando {st.get('done', 0)}/{st.get('pending', 0)} · {os.path.basename(st.get('current', ''))}"
  if state == "paused": return "Indexação pausada"
  if state == "offline": return "Embeddings offline · busca só por palavras"
  stats = self.status_db.stats()
  if self.worker and getattr(self.worker, "searcher", None) and self.worker.searcher.semantic_error: return "Busca semântica indisponível · só palavras"
  return f"{stats['files']:,} itens indexados".replace(",", ".") if stats["files"] else "Índice vazio · rode garimpo index"

 def open_with(self, text):
  if not self.window: self.window = Palette(self)
  self.start_hidden = False
  if not self.window.get_visible(): self.window.summon()
  self.window.entry.set_text(text); self.window.entry.set_position(-1)

 def do_activate(self):
  if not self.window: self.window = Palette(self)
  if self.start_hidden: self.start_hidden = False; return
  if self.window.get_visible(): self.window.dismiss()
  else: self.window.summon()

def main(hidden=False):
 return App(hidden).run([])
