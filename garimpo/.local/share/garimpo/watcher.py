"""Live updates: inotify (through ctypes, no extra dependency) on every folder the indexer reads.

New or changed files become searchable within seconds instead of waiting for the next full pass."""
import ctypes, errno, os, struct, subprocess, threading
from pathlib import Path
from indexer import dir_ok, file_kind, git_files, is_dataset, is_project

IN_CLOSE_WRITE, IN_MOVED_FROM, IN_MOVED_TO, IN_CREATE, IN_DELETE = 0x8, 0x40, 0x80, 0x100, 0x200
IN_DELETE_SELF, IN_MOVE_SELF, IN_Q_OVERFLOW, IN_IGNORED, IN_ONLYDIR, IN_ISDIR = 0x400, 0x800, 0x4000, 0x8000, 0x01000000, 0x40000000
MASK = IN_CLOSE_WRITE | IN_MOVED_FROM | IN_MOVED_TO | IN_CREATE | IN_DELETE | IN_DELETE_SELF | IN_MOVE_SELF | IN_ONLYDIR
EVENT = struct.Struct("iIII")

def _scope_root(path, cfg):
 """(scope, root) owning a path; code roots win, like in the full walk."""
 for scope, roots in (("code", cfg["code_roots"]), ("files", cfg["roots"])):
  for root in roots:
   if path == root or path.is_relative_to(root):
    if scope == "files" and any(path == r or path.is_relative_to(r) for r in cfg["code_roots"]): return None, None
    return scope, root
 return None, None

def _repo(path, root):
 """Nearest git repository containing path, not above the code root."""
 for d in [path, *path.parents]:
  if (d / ".git").exists(): return d
  if d == root: return None
 return None

def git_ignored(repo, path):
 return subprocess.run(["git", "-C", str(repo), "check-ignore", "-q", str(path)], capture_output=True, timeout=10).returncode == 0

def dir_allowed(d, cfg):
 """Would the full walk descend into this folder?"""
 scope, root = _scope_root(d, cfg)
 if not root: return False
 repo = _repo(d, root) if scope == "code" else None
 cur = root
 for part in d.relative_to(root).parts:
  cur = cur / part
  if repo and cur != repo and cur.is_relative_to(repo):
   if part == ".git" or not dir_ok(part.lstrip("."), cur, cfg["exclude"]): return False
  elif not dir_ok(part, cur, cfg["exclude"]): return False
 return not (repo and d != repo and git_ignored(repo, d))

def classify(path, cfg):
 """(scope, kind) when a single file belongs in the index, else None — the same rules as indexer.walk."""
 scope, root = _scope_root(path, cfg)
 if not root or path == root or not dir_allowed(path.parent, cfg): return None
 repo = _repo(path.parent, root) if scope == "code" else None
 if repo:
  if git_ignored(repo, path): return None
 elif path.name.startswith("."): return None
 limited = dataset = False
 if scope == "files":
  for d in [path.parent, *path.parent.parents]:
   try: entries = list(os.scandir(d))
   except OSError: return None
   if d == path.parent:
    dataset = is_dataset(d, [e.name for e in entries if e.is_file()], cfg["roots"])
   if is_project(d, [e.name for e in entries if e.is_dir()], [e.name for e in entries if not e.is_dir()]): limited = True; break
   if d == root: break
 k = file_kind(path, scope, cfg["exclude"], limited, dataset)
 return (scope, k) if k else None

def watch_dirs(cfg, top=None):
 """Every folder the full walk descends into (optionally only below `top`)."""
 starts = [top] if top else [*cfg["code_roots"], *cfg["roots"]]
 for start in starts:
  if not start.is_dir() or not dir_allowed(start, cfg): continue
  scope, root = _scope_root(start, cfg)
  for dirpath, dirs, _ in os.walk(start):
   here = Path(dirpath)
   if scope == "files" and any(here == r or here.is_relative_to(r) for r in cfg["code_roots"]): dirs[:] = []; continue
   yield here
   if scope == "code" and (here / ".git").exists() and (listed := git_files(here)) is not None:
    dirs[:] = []
    yield from sorted({p.parent for p in listed if p.parent != here and dir_allowed(p.parent, cfg)})
    continue
   dirs[:] = [d for d in dirs if dir_ok(d, here / d, cfg["exclude"])]

class Inotify:
 def __init__(self):
  self.libc = ctypes.CDLL("libc.so.6", use_errno=True)
  self.fd = self.libc.inotify_init1(os.O_CLOEXEC)
  if self.fd < 0: raise OSError(ctypes.get_errno(), "inotify_init1")

 def add(self, path):
  wd = self.libc.inotify_add_watch(self.fd, os.fsencode(path), MASK)
  return wd if wd >= 0 else -ctypes.get_errno()

 def events(self):
  """Block until events arrive; yield (wd, mask, name)."""
  data = os.read(self.fd, 256 * 1024)
  i = 0
  while i + EVENT.size <= len(data):
   wd, mask, _cookie, size = EVENT.unpack_from(data, i)
   name = data[i + EVENT.size:i + EVENT.size + size].split(b"\0", 1)[0]
   yield wd, mask, os.fsdecode(name)
   i += EVENT.size + size

class Watcher(threading.Thread):
 """Feeds changed paths to `notify(path)`; asks for a full rescan when the kernel queue overflows."""
 def __init__(self, cfg, notify, rescan, log=print):
  super().__init__(daemon=True, name="garimpo-watcher")
  self.cfg, self.notify, self.rescan, self.log = cfg, notify, rescan, log
  self.ino, self.wds, self.full = Inotify(), {}, False

 def watch_tree(self, top=None):
  for d in watch_dirs(self.cfg, top):
   wd = self.ino.add(d)
   if wd >= 0: self.wds[wd] = d
   elif wd == -errno.ENOSPC and not self.full:
    self.full = True
    self.log("[garimpo] limite de inotify atingido (fs.inotify.max_user_watches); o restante segue pela varredura periódica")

 def run(self):
  self.watch_tree()
  self.log(f"[garimpo] monitorando {len(self.wds)} pastas em tempo real")
  while True:
   for wd, mask, name in self.ino.events():
    if mask & IN_Q_OVERFLOW: self.rescan(); continue
    base = self.wds.get(wd)
    if mask & IN_IGNORED: self.wds.pop(wd, None); continue
    if base is None: continue
    path = base / name if name else base
    if mask & IN_ISDIR and mask & (IN_CREATE | IN_MOVED_TO):
     if dir_allowed(path, self.cfg):  # new folder (unzipped, moved in): watch it and index its files
      self.watch_tree(path)
      for dirpath, _, names in os.walk(path):
       for n in names: self.notify(Path(dirpath) / n)
    elif mask & (IN_CLOSE_WRITE | IN_MOVED_TO | IN_DELETE | IN_MOVED_FROM | IN_DELETE_SELF | IN_MOVE_SELF):
     self.notify(path)
