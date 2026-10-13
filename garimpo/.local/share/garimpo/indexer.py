"""Walk the configured folders and keep the index in sync. Read-only: files are never modified."""
import fnmatch, json, os, re, subprocess, threading, time
from collections import Counter
from pathlib import Path
import config, readers
from embed import EmbedError

SKIP_DIRS = {"node_modules", "__pycache__", "venv", ".venv", "env", "site-packages", "dist", "build", "target",
             "vendor", "Pods", "DerivedData", "cache", "Cache", "caches", "tmp", "lost+found", "secrets", "secret"}
SENSITIVE = ["*.pem", "*.key", "*.p12", "*.pfx", "*.kdbx", "*.keystore", "*.jks", "id_rsa*", "id_ed25519*", "id_ecdsa*",
             ".env", ".env.*", "*credential*", "*secret*", "*password*", "*senha*", "*.gpg", "*.asc", "*.ovpn", "*token*"]
MAX_TEXT = 8 * 1024 * 1024
MAX_VECTOR_CHUNKS = 300  # long logs/exports: the rest stays searchable by exact words
MAX_IMAGE = 60 * 1024 * 1024
PROJECT_MARKERS = {".git", "package.json", "pyproject.toml", "setup.py", "Cargo.toml", "go.mod", "pubspec.yaml",
                   "CMakeLists.txt", "Makefile", "platformio.ini", "requirements.txt", "build.gradle", "pom.xml"}
DATASET_SIZE = 200  # this many files of mostly one type directly inside: data, not documents
DOCUMENT_KINDS = {"image", "pdf", "office"}
NAMED_OTHER = {".zip", ".rar", ".7z", ".tar", ".gz", ".xz", ".apk", ".iso", ".deb", ".exe", ".svg", ".psd", ".xcf", ".fig",
               ".riv", ".blend", ".doc", ".xls", ".ppt", ".mobi", ".djvu", ".sqlite", ".db", ".ttf", ".otf", ".ai", ".sketch"}
DATA_EXTS = {".xlsx", ".ods", ".csv", ".tsv"}  # tables are data: exact words only, like DigUp's numeric text
QUALITY = 1  # bump to clean an existing index: vectors only for prose, confident OCR, content fingerprints
# Cheap and high-value first: names, then pictures (~1-2 s each), then documents, then sound and video.
PRIORITY = {"other": 0, "image": 1, "text": 2, "office": 2, "code": 2, "pdf": 2, "audio": 3, "video": 3}

def sensitive(name, extra=()):
 low = name.lower()
 return any(fnmatch.fnmatch(low, p) for p in [*SENSITIVE, *extra])

def embeddable(text):
 """Worth a vector? Numbers, data dumps, logs and OCR noise are found by exact words only."""
 return not readers.mostly_numeric(text) and readers.prose(text)

def git_files(repo):
 """Tracked and untracked-but-not-ignored files of a repository (respects .gitignore)."""
 r = subprocess.run(["git", "-C", str(repo), "ls-files", "-co", "--exclude-standard", "-z"], capture_output=True, timeout=60)
 return [repo / p for p in r.stdout.decode(errors="replace").split("\0") if p] if r.returncode == 0 else None

def is_project(here, dirs, names):
 entries = set(dirs) | set(names)
 return bool(entries & PROJECT_MARKERS) or {"bin", "lib"} <= entries

def dir_ok(name, path, extra):
 """Folders never indexed nor watched: hidden, dependencies, caches, secrets, user exclusions."""
 return not name.startswith(".") and name not in SKIP_DIRS and "cache" not in name.lower() and not sensitive(name, extra) \
        and not any(fnmatch.fnmatch(str(path), p) for p in extra)

def is_dataset(here, names, roots):
 return len(names) >= DATASET_SIZE and here not in roots and \
        max(Counter(Path(n).suffix.lower() for n in names).values()) >= 0.8 * len(names)

def file_kind(path, scope, extra, limited=False, dataset=False):
 """Kind of an indexable file, or None. Shared by the full walk and the live watcher."""
 if sensitive(path.name, extra) or any(fnmatch.fnmatch(str(path), p) for p in extra): return None
 k = readers.kind(path)
 if scope == "code": return k if k in ("code", "text") else None
 if k == "code": return None  # source code only lives in the opt-in code index
 if (limited or dataset) and k not in DOCUMENT_KINDS: return None
 if k == "other" and path.suffix.lower() not in NAMED_OTHER: return None
 return k

def walk(cfg):
 """Yield (path, scope, kind) for every indexable file.

 Inside code projects, software trees and dataset-like folders only pictures, PDFs and
 documents are read in the files scope; their source code belongs to the opt-in code index."""
 extra = cfg["exclude"]
 seen, restricted = set(), set()
 for scope, roots in (("code", cfg["code_roots"]), ("files", cfg["roots"])):
  for root in roots:
   if not root.is_dir(): continue
   for dirpath, dirs, names in os.walk(root):
    here = Path(dirpath)
    if scope == "files" and any(here == r or r in here.parents for r in cfg["code_roots"]):
     dirs[:] = []; continue
    limited = here.parent in restricted or (scope == "files" and is_project(here, dirs, names))
    if limited: restricted.add(here)
    dataset = is_dataset(here, names, roots)
    dirs[:] = [d for d in dirs if dir_ok(d, here / d, extra)]
    from_git = False
    if scope == "code" and (here / ".git").exists():
     listed = git_files(here)
     if listed is not None:
      dirs[:] = []; from_git = True  # .gitignore decides; tracked dot-folders (.github, .config) are source
      names = [str(p.relative_to(here)) for p in listed]
    for name in names:
     path = here / name
     if path in seen: continue
     if any(part.startswith(".") for part in Path(name).parts) and not from_git: continue
     k = file_kind(path, scope, extra, limited, dataset)
     if k is None: continue
     seen.add(path)
     yield path, scope, k

class Indexer:
 def __init__(self, cfg, store, embedder, log=print):
  self.cfg, self.store, self.embedder, self.log = cfg, store, embedder, log
  self.langs = readers.ocr_langs() if cfg["ocr"] else None
  self.last_bump = 0.0
  self.use_vectors = False
  self.pending, self.pending_lock, self.draining = {}, threading.Lock(), False
  self.rescan_now = threading.Event()

 # ── live changes (inotify) ──
 def notify(self, path):
  """Called from the watcher thread: remember the path; handled once it has been quiet for a moment."""
  with self.pending_lock: self.pending[str(path)] = time.time()

 def fresh(self, path):
  """Already indexed in its current version (by the current model when it is available)?"""
  row = self.store.file(path)
  try: st = path.stat()
  except OSError: return False
  return bool(row) and row[1] == st.st_mtime and row[2] == st.st_size and row[3] != "indexing" \
         and (row[5] == self.cfg["model"] or not self.use_vectors)

 def drain(self, quiet=1.5):
  """Index files changed since the watcher saw them — between files and even between batches of a big one."""
  if self.draining or not self.pending: return
  from watcher import classify
  now = time.time()
  with self.pending_lock:
   due = [k for k, t in self.pending.items() if now - t >= quiet]  # downloads finish writing first
   for k in due: del self.pending[k]
  if not due: return
  self.draining, changed = True, False
  try:
   for key in sorted(due):
    path = Path(key)
    if not path.exists():
     changed |= self.store.remove(key) | self.store.remove_prefix(key + "/")
     continue
    if not path.is_file(): continue
    found = classify(path, self.cfg)
    if not found: changed |= self.store.remove(key); continue
    if self.fresh(path): continue
    self.log(f"[garimpo] alterado: {key}")
    try: self.process(path, *found, self.use_vectors); changed = True
    except EmbedError as e:
     if e.offline: self.notify(path); break  # server restarting: retry later
     self._mark_error(key)
    except Exception as e: self.log(f"[garimpo] erro em {key}: {e!r}"); self._mark_error(key)
  finally:
   self.draining = False
  if changed: self._bump(force=True)

 def start_watching(self):
  try:
   from watcher import Watcher
   Watcher(self.cfg, self.notify, self.rescan_now.set, self.log).start()
  except OSError as e: self.log(f"[garimpo] inotify indisponível ({e}); usando só a varredura periódica")

 def status(self, state, **extra):
  self.store.set("status", json.dumps(dict(state=state, at=time.time(), **extra)))

 def _bump(self, force=False):
  if force or time.time() - self.last_bump > 4: self.store.bump(); self.last_bump = time.time()

 def online(self):
  ok, msg = self.embedder.status()
  self.log(f"[garimpo] embeddings: {msg}" if ok else f"[garimpo] embeddings indisponíveis: {msg} (indexando só texto exato)")
  return ok

 def _embed_rows(self, title, pieces, use_vectors, limit=MAX_VECTOR_CHUNKS):
  """pieces: [(loc, text)] -> rows ready for Store.add_chunks."""
  rows, todo = [], []
  for loc, text in pieces:
   if use_vectors and (limit is None or len(todo) < limit) and embeddable(text): todo.append((loc, text))
   else: rows.append((loc, text, None, text))
  for i in range(0, len(todo), 16):
   self.drain()
   batch = todo[i:i + 16]
   vecs = self.embedder.documents([(title, t) for _, t in batch])
   rows += [(loc, text, vec, text) for (loc, text), vec in zip(batch, vecs)]
  return rows

 def process(self, path, scope, k, use_vectors):
  st = path.stat()
  model = self.cfg["model"] if use_vectors else ""
  fid = self.store.upsert_file(path, st.st_mtime, st.st_size, k, scope, "indexing", model)
  self.store.set_digest(fid, readers.digest(path))
  label = readers.name_text(path)
  fts_name = f"{path.name} {re.sub(r'[_.-]+', ' ', path.stem)} {path.parent.name}"
  name_vec = self.embedder.documents([(path.name, f"{label} ({path.parent.name})")])[0] if use_vectors and label else None
  self.store.add_chunks(fid, [(None, path.name, name_vec, fts_name)], model)
  state, done_pages = "done", None
  if k in ("text", "code") and st.st_size <= MAX_TEXT:
   pieces = readers.read_code(path) if k == "code" else readers.chunks(readers.read_text(path))
   self.store.add_chunks(fid, self._embed_rows(path.name, pieces, use_vectors and path.suffix.lower() not in DATA_EXTS), model)
  elif k == "office" and st.st_size <= MAX_TEXT * 8:
   self.store.add_chunks(fid, self._embed_rows(path.name, readers.read_office(path), use_vectors and path.suffix.lower() not in DATA_EXTS), model)
  elif k == "pdf":
   pages = readers.pdf_pages(path)
   last = min(pages, self.cfg["pdf_first_pages"], self.cfg["pdf_max_pages"])
   if last: self.store.add_chunks(fid, self._embed_rows(path.name, readers.read_pdf(path, 1, last, self.langs), use_vectors, None), model)
   done_pages = last
   if pages > last and last < self.cfg["pdf_max_pages"]: state = "partial"
  elif k == "image" and st.st_size <= MAX_IMAGE:
   rows = self.media_rows(path, k) if use_vectors else []
   self.store.add_chunks(fid, rows + self.ocr_rows(path, use_vectors), model)
  elif k in ("video", "audio") and use_vectors:
   self.store.add_chunks(fid, self.media_rows(path, k), model)
  self.store.set_state(fid, state, done_pages)

 def ocr_rows(self, path, use_vectors):
  if not (self.langs and readers.wants_ocr(path)): return []
  text = readers.ocr(path, self.langs)
  return self._embed_rows(path.name, [(0, t) for _, t in readers.chunks(text)], use_vectors) if len(text) >= 20 else []

 def upgrade(self):
  """One-off cleanup of an index built by an older version (see QUALITY)."""
  if int(self.store.get("quality") or 0) >= QUALITY: return
  db = self.store.db
  self.log("[garimpo] limpando o índice: vetores só para texto corrido, OCR confiável, impressões digitais")
  noisy = [cid for cid, text in db.execute("select id,text from chunks where modality='t' and loc is not null and vec is not null")
           if not embeddable(text or "")]
  with db: db.executemany("update chunks set vec=null, model=null where id=?", [(c,) for c in noisy])
  for fid, key in db.execute("select id,path from files where digest is null").fetchall():
   try: self.store.set_digest(fid, readers.digest(Path(key)))
   except OSError: pass
  if self.langs:
   scanned = db.execute("select distinct f.id,f.path,f.model from files f join chunks c on c.file_id=f.id "
                        "where f.kind='image' and c.modality='t' and c.loc is not null").fetchall()
   for fid, key, model in scanned:
    self.drain()
    try: rows = self.ocr_rows(Path(key), bool(model))
    except Exception as e: self.log(f"[garimpo] erro em {key}: {e!r}"); continue
    self.store.replace_text(fid, rows, model)
  self.store.set("quality", QUALITY); self._bump(force=True)
  self.log(f"[garimpo] {len(noisy)} trechos de dados/ruído agora só por palavra exata")

 def media_rows(self, path, k):
  """Image, video-frame and sound vectors in the shared text/image/audio space."""
  rows, cfg, emb = [], self.cfg, self.embedder
  if k == "image" and cfg["images"] and path.stat().st_size <= MAX_IMAGE and (jpg := readers.image_bytes(path)):
   if (vec := emb.image(jpg)) is not None: rows.append((0, "", vec, None, "i"))
  if k == "video" and cfg["videos"] and cfg["images"]:
   for sec, jpg in readers.video_frames(path, cfg["video_max_frames"]):
    self.drain()
    if (vec := emb.image(jpg)) is None: break
    rows.append((sec, "", vec, None, "i"))
  if (k == "audio" or (k == "video" and cfg["videos"])) and cfg["audio"]:
   for sec, wav in readers.audio_windows(path, cfg["audio_max_windows"]):
    self.drain()
    if (vec := emb.audio(wav)) is None: break
    rows.append((sec, "", vec, None, "a"))
  return rows

 def reembed(self, path, k):
  """The file is unchanged but was indexed without (or with another) model: reuse the extracted text."""
  fid, *_ = self.store.file(path)
  label = readers.name_text(path)
  data = path.suffix.lower() in DATA_EXTS
  todo = []
  for cid, loc, text in self.store.chunks_of(fid):
   if data and loc is not None: continue
   if loc is None and label: todo.append((cid, f"{label} ({path.parent.name})"))
   elif loc is not None and text and embeddable(text) and (k == "pdf" or len(todo) <= MAX_VECTOR_CHUNKS): todo.append((cid, text))
  pairs = []
  for i in range(0, len(todo), 16):
   self.drain()
   batch = todo[i:i + 16]
   pairs += zip([c for c, _ in batch], self.embedder.documents([(path.name, t) for _, t in batch]))
  self.store.set_vectors(fid, pairs, self.cfg["model"])
  if k in ("image", "video", "audio"):
   self.store.drop_visual(fid); self.store.add_chunks(fid, self.media_rows(path, k), self.cfg["model"])

 def continue_pdf(self, path, use_vectors, block=100):
  fid, _, _, _, done, model = self.store.file(path)
  pages = readers.pdf_pages(path)
  last = min(pages, done + block, self.cfg["pdf_max_pages"])
  self.store.add_chunks(fid, self._embed_rows(path.name, readers.read_pdf(path, done + 1, last, self.langs), use_vectors, None), model)
  self.store.set_state(fid, "partial" if last < min(pages, self.cfg["pdf_max_pages"]) else "done", last)

 def paused(self):
  if (config.STATE / "paused").exists(): return True
  if self.cfg["pause_on_battery"]:
   online = [p for p in Path("/sys/class/power_supply").glob("A*/online")]
   if online and all(p.read_text().strip() == "0" for p in online): return True
  return False

 def cycle(self):
  """One full pass: remove deleted files, index new/changed ones, then continue long PDFs."""
  use_vectors = self.use_vectors = self.online()
  if use_vectors: self.upgrade()
  known = self.store.files()
  found, todo = set(), []
  for path, scope, k in walk(self.cfg):
   key = str(path); found.add(key)
   try: st = path.stat()
   except OSError: continue
   row = known.get(key)
   unchanged = row and row[0] == st.st_mtime and row[1] == st.st_size and row[2] != "indexing"
   if unchanged and (row[3] == self.cfg["model"] or not use_vectors): continue
   todo.append((PRIORITY.get(k, 1), -st.st_mtime, key, scope, k, bool(unchanged and row[2] != "error")))
  for key in set(known) - found:
   if any(Path(key).is_relative_to(r) and r.is_dir() for r in self.cfg["roots"] + self.cfg["code_roots"]) or not Path(key).exists():
    self.store.remove(key)
  todo.sort()
  self.log(f"[garimpo] {len(found)} arquivos, {len(todo)} para indexar")
  for n, (_, _, key, scope, k, unchanged) in enumerate(todo, 1):
   while self.paused(): self.status("paused", pending=len(todo) - n + 1); time.sleep(10)
   self.drain()
   if not Path(key).exists() or (not unchanged and self.fresh(Path(key))): continue  # handled live meanwhile
   self.status("indexing", done=n - 1, pending=len(todo), current=key)
   try: self.reembed(Path(key), k) if unchanged else self.process(Path(key), scope, k, use_vectors)
   except EmbedError as e:
    if e.offline: self.log(f"[garimpo] {e}"); self.status("offline", message=str(e)); return False
    self.log(f"[garimpo] erro em {key}: {e}"); self._mark_error(key)
   except Exception as e:  # unreadable or malformed file: skip it, keep going
    self.log(f"[garimpo] erro em {key}: {e!r}"); self._mark_error(key)
   self._bump()
  partial = [r[0] for r in self.store.db.execute("select path from files where state='partial'")]
  for key in partial:
   self.drain()
   self.status("indexing", done=0, pending=len(partial), current=key)
   try: self.continue_pdf(Path(key), use_vectors)
   except Exception as e: self.log(f"[garimpo] erro em {key}: {e!r}"); self._mark_error(key)
   self._bump()
  self._bump(force=True)
  self.status("idle", **self.store.stats())
  return True

 def _mark_error(self, key):
  row = self.store.file(key)
  if row: self.store.set_state(row[0], "error")

 def watch(self):
  """Full pass, then react to inotify events until the periodic safety rescan (or a queue overflow)."""
  self.start_watching()
  while True:
   try: ok = self.cycle()
   except Exception as e: ok = False; self.log(f"[garimpo] ciclo falhou: {e!r}")
   deadline = time.time() + (self.cfg["rescan_seconds"] if ok else 15)  # embedding server restarting: retry soon
   while time.time() < deadline and not self.rescan_now.is_set():
    if self.pending and not self.paused():
     self.use_vectors = self.use_vectors or self.embedder.status()[0]
     self.drain()
    time.sleep(0.5)
   self.rescan_now.clear()
