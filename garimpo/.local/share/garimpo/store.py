"""One SQLite file: file catalogue, chunks with float16 vectors and an FTS5 keyword index."""
import sqlite3, threading, unicodedata
import numpy as np

SCHEMA = """
create table if not exists files(
 id integer primary key, path text unique not null, mtime real, size integer,
 kind text, scope text, state text, done_pages integer default 0, model text);
create table if not exists chunks(
 id integer primary key, file_id integer not null references files(id) on delete cascade,
 loc integer, text text, vec blob, model text, modality text default 't');
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
  if "modality" not in [r[1] for r in self.db.execute("pragma table_info(chunks)")]:  # index from an older version
   with self.db:
    self.db.execute("alter table chunks add column modality text default 't'")
    self.db.execute("update chunks set modality = case (select kind from files where id=file_id) when 'audio' then 'a' else 'i' end "
                    "where coalesce(text,'')='' and loc is not null")
  if "digest" not in [r[1] for r in self.db.execute("pragma table_info(files)")]:
   with self.db: self.db.execute("alter table files add column digest text")
  if "hub" not in [r[1] for r in self.db.execute("pragma table_info(chunks)")]:
   with self.db: self.db.execute("alter table chunks add column hub real")  # see search.HUB_K
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

 def reindex_words(self, rows):
  """rows: [(chunk_id, searchable_text)] — replace their keyword entries (NFC)."""
  with self.db:
   self.db.executemany("delete from chunks_fts where rowid=?", [(c,) for c, _ in rows])
   self.db.executemany("insert into chunks_fts(rowid,text) values(?,?)", [(c, unicodedata.normalize("NFC", t)) for c, t in rows])

 def set_digest(self, file_id, digest):
  with self.db: self.db.execute("update files set digest=? where id=?", (digest, file_id))

 def add_chunks(self, file_id, rows, model):
  """rows: [(loc, text, vec_or_None, searchable_text[, modality])] — modality: t(ext), i(mage) or a(udio)"""
  with self.db:
   for loc, text, vec, fts, *rest in rows:
    blob = None if vec is None else np.asarray(vec, dtype=np.float16).tobytes()
    cid = self.db.execute("insert into chunks(file_id,loc,text,vec,model,modality) values(?,?,?,?,?,?)",
                          (file_id, loc, text, blob, model if blob else None, rest[0] if rest else "t")).lastrowid
    # NFC: macOS/phone file names arrive decomposed ("a" + combining tilde) and FTS5 would split
    # "Plutão" into "pluta" + "o".
    if fts: self.db.execute("insert into chunks_fts(rowid,text) values(?,?)", (cid, unicodedata.normalize("NFC", fts)))

 def chunks_of(self, file_id):
  return self.db.execute("select id,loc,text from chunks where file_id=?", (file_id,)).fetchall()

 def drop_visual(self, file_id):
  """Remove image/frame vectors (chunks without text) so they can be recomputed."""
  with self.db: self.db.execute("delete from chunks where file_id=? and modality in ('i','a')", (file_id,))

 def set_vectors(self, file_id, pairs, model):
  """Attach vectors to existing chunks and mark the file as embedded by `model`."""
  with self.db:
   self.db.executemany("update chunks set vec=?, model=?, hub=null where id=?",
                       [(np.asarray(v, dtype=np.float16).tobytes(), model, cid) for cid, v in pairs])
   self.db.execute("update files set model=? where id=?", (model, file_id))

 def replace_text(self, file_id, rows, model):
  """Swap a file's text passages (e.g. redone OCR), keeping its name and picture vectors."""
  with self.db:
   ids = [r[0] for r in self.db.execute("select id from chunks where file_id=? and modality='t' and loc is not null", (file_id,))]
   self.db.executemany("delete from chunks_fts where rowid=?", [(i,) for i in ids])
   self.db.executemany("delete from chunks where id=?", [(i,) for i in ids])
  self.add_chunks(file_id, rows, model)

 def _delete_chunks(self, file_id):
  ids = [r[0] for r in self.db.execute("select id from chunks where file_id=?", (file_id,))]
  self.db.executemany("delete from chunks_fts where rowid=?", [(i,) for i in ids])
  self.db.execute("delete from chunks where file_id=?", (file_id,))

 def remove(self, path):
  """Forget a file; True if it was indexed."""
  with self.db:
   row = self.file(path)
   if row: self._delete_chunks(row[0]); self.db.execute("delete from files where id=?", (row[0],))
  return bool(row)

 def remove_prefix(self, prefix):
  """Forget every file below a deleted or moved-away folder."""
  paths = [r[0] for r in self.db.execute("select path from files where substr(path,1,?)=?", (len(prefix), prefix))]
  for p in paths: self.remove(p)
  return bool(paths)

 def matrix(self, scope, model):
  """Cached (chunk_ids, float32 matrix, modalities) for the scope; rebuilt only when the index changes."""
  gen = self.generation()
  cached = self._matrix.get(scope)
  if cached and cached[0] == gen: return cached[1:4]
  with self.lock:
   rows = self.db.execute("select c.id,c.vec,c.modality,c.hub from chunks c join files f on f.id=c.file_id "
                          "where f.scope=? and c.vec is not null and c.model=?", (scope, model)).fetchall()
  ids = np.fromiter((r[0] for r in rows), dtype=np.int64, count=len(rows))
  mat = np.frombuffer(b"".join(r[1] for r in rows), dtype=np.float16).reshape(len(rows), -1).astype(np.float32) if rows else np.zeros((0, 1), np.float32)
  mods = np.array([r[2] or "t" for r in rows])
  hubs = np.array([np.nan if r[3] is None else r[3] for r in rows], dtype=np.float32)
  self._matrix[scope] = (gen, ids, mat, mods, hubs)
  return ids, mat, mods

 def media_counts(self):
  """{file_id: number of picture/sound vectors} — a video has dozens of chances to look relevant."""
  gen = self.generation()
  if getattr(self, "_counts", (None,))[0] != gen:
   self._counts = (gen, dict(self.db.execute("select file_id, count(*) from chunks where modality in ('i','a') "
                                             "and vec is not null group by file_id")))
  return self._counts[1]

 def hubs(self, scope):
  """Stored hub values aligned with the last matrix(scope); NaN where not computed yet."""
  return self._matrix[scope][4]

 def set_hubs(self, pairs, key):
  """Persist hub values; `key` names the probes they were computed with (a new key clears old values)."""
  with self.db:
   if self.get("hub_key") != key:
    self.db.execute("update chunks set hub=null")
    self.db.execute("insert or replace into meta values('hub_key',?)", (key,))
   self.db.executemany("update chunks set hub=? where id=?", [(float(h), int(c)) for c, h in pairs])

 def keyword(self, match, scope, limit=200):
  try:
   return self.db.execute("select c.id, bm25(chunks_fts) from chunks_fts join chunks c on c.id=chunks_fts.rowid "
                          "join files f on f.id=c.file_id where chunks_fts match ? and f.scope=? "
                          "order by bm25(chunks_fts) limit ?", (match, scope, limit)).fetchall()
  except sqlite3.OperationalError: return []

 def vocabulary(self):
  """{word: number of passages} of the keyword index (accent-folded, as FTS5 stores it)."""
  self.db.execute("create virtual table if not exists temp.chunks_vocab using fts5vocab(main, chunks_fts, 'row')")
  with self.lock: return dict(self.db.execute("select term, doc from temp.chunks_vocab"))

 def chunk_info(self, ids):
  ids = sorted({int(i) for i in ids})
  if not ids: return {}
  marks = ",".join("?" * len(ids))
  rows = self.db.execute(f"select c.id,c.file_id,c.loc,c.text,f.path,f.kind,f.mtime,c.vec is not null,f.digest "
                         f"from chunks c join files f on f.id=c.file_id where c.id in ({marks})", ids)
  return {r[0]: dict(file_id=r[1], loc=r[2], text=r[3] or "", path=r[4], kind=r[5], mtime=r[6], has_vec=bool(r[7]), digest=r[8])
          for r in rows}

 def stats(self):
  total, done = self.db.execute("select count(*), sum(state in ('done','error','skip')) from files").fetchone()
  return dict(files=total or 0, done=done or 0, chunks=self.db.execute("select count(*) from chunks").fetchone()[0])
