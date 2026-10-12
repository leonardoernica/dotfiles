"""One SQLite file: file catalogue, chunks with float16 vectors and an FTS5 keyword index."""
import sqlite3, threading
import numpy as np

SCHEMA = """
create table if not exists files(
 id integer primary key, path text unique not null, mtime real, size integer,
 kind text, scope text, state text, done_pages integer default 0, model text);
create table if not exists chunks(
 id integer primary key, file_id integer not null references files(id) on delete cascade,
 loc integer, text text, vec blob, model text);
create index if not exists chunks_file on chunks(file_id);
create virtual table if not exists chunks_fts using fts5(
 text, content='', contentless_delete=1, tokenize='unicode61 remove_diacritics 2');
create table if not exists meta(key text primary key, value text);
"""

class Store:
 def __init__(self, path):
  path.parent.mkdir(parents=True, exist_ok=True)
  self.db = sqlite3.connect(path, timeout=30, check_same_thread=False)
  self.db.execute("pragma journal_mode=wal"); self.db.execute("pragma foreign_keys=on")
  self.db.executescript(SCHEMA)
  self.lock = threading.Lock()
  self._matrix = {}  # scope -> (generation, ids, matrix)

 def generation(self): return int(self.get("generation") or 0)
 def get(self, key):
  row = self.db.execute("select value from meta where key=?", (key,)).fetchone()
  return row[0] if row else None
 def set(self, key, value):
  with self.db: self.db.execute("insert or replace into meta values(?,?)", (key, str(value)))
 def bump(self): self.set("generation", self.generation() + 1)

 def file(self, path): return self.db.execute("select id,mtime,size,state,done_pages,model from files where path=?", (str(path),)).fetchone()
 def files(self, scope=None):
  sql, args = "select path,mtime,size,state,model from files", ()
  if scope: sql, args = sql + " where scope=?", (scope,)
  return {r[0]: r[1:] for r in self.db.execute(sql, args)}

 def upsert_file(self, path, mtime, size, kind, scope, state, model):
  with self.db:
   row = self.file(path)
   if row:
    self._delete_chunks(row[0])
    self.db.execute("update files set mtime=?,size=?,kind=?,scope=?,state=?,done_pages=0,model=? where id=?",
                    (mtime, size, kind, scope, state, model, row[0]))
    return row[0]
   return self.db.execute("insert into files(path,mtime,size,kind,scope,state,model) values(?,?,?,?,?,?,?)",
                          (str(path), mtime, size, kind, scope, state, model)).lastrowid

 def set_state(self, file_id, state, done_pages=None):
  with self.db:
   self.db.execute("update files set state=? where id=?", (state, file_id))
   if done_pages is not None: self.db.execute("update files set done_pages=? where id=?", (done_pages, file_id))

 def add_chunks(self, file_id, rows, model):
  """rows: [(loc, text, vec_or_None, searchable_text)]"""
  with self.db:
   for loc, text, vec, fts in rows:
    blob = None if vec is None else np.asarray(vec, dtype=np.float16).tobytes()
    cid = self.db.execute("insert into chunks(file_id,loc,text,vec,model) values(?,?,?,?,?)",
                          (file_id, loc, text, blob, model if blob else None)).lastrowid
    if fts: self.db.execute("insert into chunks_fts(rowid,text) values(?,?)", (cid, fts))

 def chunks_of(self, file_id):
  return self.db.execute("select id,loc,text from chunks where file_id=?", (file_id,)).fetchall()

 def drop_visual(self, file_id):
  """Remove image/frame vectors (chunks without text) so they can be recomputed."""
  with self.db: self.db.execute("delete from chunks where file_id=? and loc is not null and coalesce(text,'')=''", (file_id,))

 def set_vectors(self, file_id, pairs, model):
  """Attach vectors to existing chunks and mark the file as embedded by `model`."""
  with self.db:
   self.db.executemany("update chunks set vec=?, model=? where id=?",
                       [(np.asarray(v, dtype=np.float16).tobytes(), model, cid) for cid, v in pairs])
   self.db.execute("update files set model=? where id=?", (model, file_id))

 def _delete_chunks(self, file_id):
  ids = [r[0] for r in self.db.execute("select id from chunks where file_id=?", (file_id,))]
  self.db.executemany("delete from chunks_fts where rowid=?", [(i,) for i in ids])
  self.db.execute("delete from chunks where file_id=?", (file_id,))

 def remove(self, path):
  with self.db:
   row = self.file(path)
   if row: self._delete_chunks(row[0]); self.db.execute("delete from files where id=?", (row[0],))

 def matrix(self, scope, model):
  """Cached (chunk_ids, float32 matrix) for the scope; rebuilt only when the index changes."""
  gen = self.generation()
  cached = self._matrix.get(scope)
  if cached and cached[0] == gen: return cached[1], cached[2]
  with self.lock:
   rows = self.db.execute("select c.id,c.vec from chunks c join files f on f.id=c.file_id "
                          "where f.scope=? and c.vec is not null and c.model=?", (scope, model)).fetchall()
  ids = np.fromiter((r[0] for r in rows), dtype=np.int64, count=len(rows))
  mat = np.frombuffer(b"".join(r[1] for r in rows), dtype=np.float16).reshape(len(rows), -1).astype(np.float32) if rows else np.zeros((0, 1), np.float32)
  self._matrix[scope] = (gen, ids, mat)
  return ids, mat

 def keyword(self, match, scope, limit=200):
  try:
   return self.db.execute("select c.id, bm25(chunks_fts) from chunks_fts join chunks c on c.id=chunks_fts.rowid "
                          "join files f on f.id=c.file_id where chunks_fts match ? and f.scope=? "
                          "order by bm25(chunks_fts) limit ?", (match, scope, limit)).fetchall()
  except sqlite3.OperationalError: return []

 def chunk_info(self, ids):
  if not len(ids): return {}
  marks = ",".join("?" * len(ids))
  rows = self.db.execute(f"select c.id,c.file_id,c.loc,c.text,f.path,f.kind,f.mtime from chunks c join files f on f.id=c.file_id where c.id in ({marks})",
                         [int(i) for i in ids])
  return {r[0]: dict(file_id=r[1], loc=r[2], text=r[3] or "", path=r[4], kind=r[5], mtime=r[6]) for r in rows}

 def stats(self):
  total, done = self.db.execute("select count(*), sum(state in ('done','error','skip')) from files").fetchone()
  return dict(files=total or 0, done=done or 0, chunks=self.db.execute("select count(*) from chunks").fetchone()[0])
