"""Walk the configured folders and keep the index in sync. Read-only: files are never modified."""
import fnmatch, json, os, re, subprocess, time
from collections import Counter
from pathlib import Path
import config, readers
from embed import EmbedError

SKIP_DIRS = {"node_modules", "__pycache__", "venv", ".venv", "env", "site-packages", "dist", "build", "target",
             "vendor", "Pods", "DerivedData", "cache", "Cache", "caches", "tmp", "lost+found", "secrets", "secret"}
SENSITIVE = ["*.pem", "*.key", "*.p12", "*.pfx", "*.kdbx", "*.keystore", "*.jks", "id_rsa*", "id_ed25519*", "id_ecdsa*",
             ".env", ".env.*", "*credential*", "*secret*", "*password*", "*senha*", "*.gpg", "*.asc", "*.ovpn", "*token*"]
MAX_TEXT = 8 * 1024 * 1024
MAX_IMAGE = 60 * 1024 * 1024
PROJECT_MARKERS = {".git", "package.json", "pyproject.toml", "setup.py", "Cargo.toml", "go.mod", "pubspec.yaml",
                   "CMakeLists.txt", "Makefile", "platformio.ini", "requirements.txt", "build.gradle", "pom.xml"}
DATASET_SIZE = 200  # this many files of mostly one type directly inside: data, not documents
DOCUMENT_KINDS = {"image", "pdf", "office"}
NAMED_OTHER = {".zip", ".rar", ".7z", ".tar", ".gz", ".xz", ".apk", ".iso", ".deb", ".exe", ".svg", ".psd", ".xcf", ".fig",
               ".riv", ".blend", ".doc", ".xls", ".ppt", ".mobi", ".djvu", ".sqlite", ".db", ".ttf", ".otf", ".ai", ".sketch"}
PRIORITY = {"other": 0, "audio": 0, "text": 1, "office": 1, "code": 1, "pdf": 1, "image": 2, "video": 3}

def sensitive(name, extra=()):
 low = name.lower()
 return any(fnmatch.fnmatch(low, p) for p in [*SENSITIVE, *extra])

def git_files(repo):
 """Tracked and untracked-but-not-ignored files of a repository (respects .gitignore)."""
 r = subprocess.run(["git", "-C", str(repo), "ls-files", "-co", "--exclude-standard", "-z"], capture_output=True, timeout=60)
 return [repo / p for p in r.stdout.decode(errors="replace").split("\0") if p] if r.returncode == 0 else None

def is_project(here, dirs, names):
 entries = set(dirs) | set(names)
 return bool(entries & PROJECT_MARKERS) or {"bin", "lib"} <= entries

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
    dataset = len(names) >= DATASET_SIZE and here not in roots and \
              max(Counter(Path(n).suffix.lower() for n in names).values()) >= 0.8 * len(names)
    dirs[:] = [d for d in dirs if not d.startswith(".") and d not in SKIP_DIRS and not sensitive(d, extra)
               and not any(fnmatch.fnmatch(str(here / d), p) for p in extra)]
    if scope == "code" and (here / ".git").exists():
     listed = git_files(here)
     if listed is not None:
      dirs[:] = []
      names = [str(p.relative_to(here)) for p in listed]
    for name in names:
     path = here / name
     if path in seen or any(part.startswith(".") for part in Path(name).parts) or sensitive(path.name, extra): continue
     if any(fnmatch.fnmatch(str(path), p) for p in extra): continue
     k = readers.kind(path)
     if scope == "code" and k not in ("code", "text"): continue
     if scope == "files" and k == "code": continue  # source code only lives in the opt-in code index
     if scope == "files" and (limited or dataset) and k not in DOCUMENT_KINDS: continue
     if k == "other" and path.suffix.lower() not in NAMED_OTHER: continue
     seen.add(path)
     yield path, scope, k

class Indexer:
 def __init__(self, cfg, store, embedder, log=print):
  self.cfg, self.store, self.embedder, self.log = cfg, store, embedder, log
  self.langs = readers.ocr_langs() if cfg["ocr"] else None
  self.last_bump = 0.0

 def status(self, state, **extra):
  self.store.set("status", json.dumps(dict(state=state, at=time.time(), **extra)))

 def _bump(self, force=False):
  if force or time.time() - self.last_bump > 4: self.store.bump(); self.last_bump = time.time()

 def online(self):
  ok, msg = self.embedder.status()
  if not ok: self.log(f"[garimpo] embeddings indisponíveis: {msg} (indexando só texto exato)")
  return ok

 def _embed_rows(self, title, pieces, use_vectors):
  """pieces: [(loc, text)] -> rows ready for Store.add_chunks."""
  rows, todo = [], []
  for loc, text in pieces:
   if use_vectors and not readers.mostly_numeric(text): todo.append((loc, text))
   else: rows.append((loc, text, None, text))
  for i in range(0, len(todo), 16):
   batch = todo[i:i + 16]
   vecs = self.embedder.documents([(title, t) for _, t in batch])
   rows += [(loc, text, vec, text) for (loc, text), vec in zip(batch, vecs)]
  return rows

 def process(self, path, scope, k, use_vectors):
  st = path.stat()
  model = self.cfg["model"] if use_vectors else ""
  fid = self.store.upsert_file(path, st.st_mtime, st.st_size, k, scope, "indexing", model)
  label = readers.name_text(path)
  fts_name = f"{path.name} {re.sub(r'[_.-]+', ' ', path.stem)} {path.parent.name}"
  name_vec = self.embedder.documents([(path.name, f"{label} ({path.parent.name})")])[0] if use_vectors and label else None
  self.store.add_chunks(fid, [(None, path.name, name_vec, fts_name)], model)
  state, done_pages = "done", None
  if k in ("text", "code") and st.st_size <= MAX_TEXT:
   pieces = readers.read_code(path) if k == "code" else readers.chunks(readers.read_text(path))
   self.store.add_chunks(fid, self._embed_rows(path.name, pieces, use_vectors), model)
  elif k == "office" and st.st_size <= MAX_TEXT * 8:
   self.store.add_chunks(fid, self._embed_rows(path.name, readers.read_office(path), use_vectors), model)
  elif k == "pdf":
   pages = readers.pdf_pages(path)
   last = min(pages, self.cfg["pdf_first_pages"], self.cfg["pdf_max_pages"])
   if last: self.store.add_chunks(fid, self._embed_rows(path.name, readers.read_pdf(path, 1, last, self.langs), use_vectors), model)
   done_pages = last
   if pages > last and last < self.cfg["pdf_max_pages"]: state = "partial"
  elif k == "image" and st.st_size <= MAX_IMAGE:
   rows = self.visual_rows(path, k) if use_vectors else []
   if self.langs and readers.wants_ocr(path):
    text = readers.ocr(path, self.langs)
    if len(text) >= 20: rows += self._embed_rows(path.name, [(0, t) for _, t in readers.chunks(text)], use_vectors)
   self.store.add_chunks(fid, rows, model)
  elif k == "video" and use_vectors:
   self.store.add_chunks(fid, self.visual_rows(path, k), model)
  self.store.set_state(fid, state, done_pages)

 def visual_rows(self, path, k):
  """Image or video-frame vectors in the shared text/image space."""
  rows = []
  if not self.cfg["images"] or self.embedder.images is False: return rows
  if k == "image" and path.stat().st_size <= MAX_IMAGE and (jpg := readers.image_bytes(path)):
   vec = self.embedder.image(jpg)
   if vec is not None: rows.append((0, "", vec, None))
  elif k == "video" and self.cfg["videos"]:
   for sec, jpg in readers.video_frames(path, self.cfg["video_max_frames"]):
    vec = self.embedder.image(jpg)
    if vec is None: break
    rows.append((sec, "", vec, None))
  return rows

 def reembed(self, path, k):
  """The file is unchanged but was indexed without (or with another) model: reuse the extracted text."""
  fid, *_ = self.store.file(path)
  label = readers.name_text(path)
  todo = []
  for cid, loc, text in self.store.chunks_of(fid):
   if loc is None and label: todo.append((cid, f"{label} ({path.parent.name})"))
   elif loc is not None and text and not readers.mostly_numeric(text): todo.append((cid, text))
  pairs = []
  for i in range(0, len(todo), 16):
   batch = todo[i:i + 16]
   pairs += zip([c for c, _ in batch], self.embedder.documents([(path.name, t) for _, t in batch]))
  self.store.set_vectors(fid, pairs, self.cfg["model"])
  if k in ("image", "video"):
   self.store.drop_visual(fid); self.store.add_chunks(fid, self.visual_rows(path, k), self.cfg["model"])

 def continue_pdf(self, path, use_vectors, block=100):
  fid, _, _, _, done, model = self.store.file(path)
  pages = readers.pdf_pages(path)
  last = min(pages, done + block, self.cfg["pdf_max_pages"])
  self.store.add_chunks(fid, self._embed_rows(path.name, readers.read_pdf(path, done + 1, last, self.langs), use_vectors), model)
  self.store.set_state(fid, "partial" if last < min(pages, self.cfg["pdf_max_pages"]) else "done", last)

 def paused(self):
  if (config.STATE / "paused").exists(): return True
  if self.cfg["pause_on_battery"]:
   online = [p for p in Path("/sys/class/power_supply").glob("A*/online")]
   if online and all(p.read_text().strip() == "0" for p in online): return True
  return False

 def cycle(self):
  """One full pass: remove deleted files, index new/changed ones, then continue long PDFs."""
  use_vectors = self.online()
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
  while True:
   try: self.cycle()
   except Exception as e: self.log(f"[garimpo] ciclo falhou: {e!r}")
   time.sleep(self.cfg["rescan_seconds"])
