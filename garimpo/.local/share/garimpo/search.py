"""Hybrid ranking: EmbeddingGemma similarity + exact words + file names, one result per file.

Every signal is put on one scale: how many standard deviations a piece stands out from the rest of
its kind (text, pictures, sound) *for this query*. Raw cosine similarities drift from query to query
(a common word lifts thousands of chunks), so a fixed cut-off let in hundreds of results for some
searches and nothing for others. Measured with `garimpo eval`."""
import base64, hashlib, os, re, unicodedata
from pathlib import Path
import numpy as np
from embed import EmbedError

# The best of n unrelated chunks already sits near z = sqrt(2 ln n) (the maximum of many draws: 4.6
# for this machine's ~43k), so a document has to come close to that and stay near the best one.
# Tuned with garimpo eval: right file first in 23/30 searches, ~11 results when nothing clearly
# matches (a fixed similarity cut-off gave 1/30 and ~14).
NOISE_FRACTION = 0.86  # x sqrt(2 ln n): z = 4.0 at 43k chunks
SPREAD_Z = 2.0
KEYWORD_Z = 1.5    # every query word in the passage, as whole words: a tie-breaker, not a trump card
RARE_HITS = 3      # an exact match in at most this many passages is specific (an order number, an error code)
NAME_Z = 2.0       # every query word in the file name
MEDIA_Z = 3.0
MEDIA_SPREAD = 1.0
MEDIA_LIMIT = 4
MEDIA_MULTI = 0.8  # x sqrt(2 ln frames): the best of 40 video frames stands out by chance alone
MEDIA_AFTER = 3    # weaker pictures still show up after at most this many documents
# Words that say what kind of file is wanted: "foto com amigos", "print do pix", "música triste".
WANTS = {"i": {"foto", "fotos", "imagem", "imagens", "print", "prints", "captura", "screenshot", "selfie", "figura", "desenho", "logo", "photo", "picture"},
         "v": {"video", "videos", "filmagem", "gravacao", "clipe"},
         "a": {"musica", "musicas", "audio", "audios", "som", "cancao", "beat", "podcast", "song"}}
MIN_SPREAD = 0.02  # tiny collections: keep z-scores finite

# Hubs: some chunks (long books, busy screenshots, short sound clips, video frames) are close to
# *every* query and used to show up for anything. Each chunk's similarity is lowered by its mean
# similarity to its nearest generic probes (CSLS, the standard fix for hubness in cross-modal search).
HUB_K = 10
PROBES = """documento foto pessoa reunião dinheiro comida cidade computador carro música natureza animal casa escola
trabalho viagem celular livro roupa saúde esporte política empresa contrato tecnologia família festa praia loja produto
gráfico tabela texto tela logotipo desenho vídeo som voz criança mulher homem rua prédio céu mapa arte jogo notícia
ciência matemática programação marketing vendas cliente banco boleto receita médico lei governo religião amor natal
estudo aula prova curso dança filme mensagem conversa internet aplicativo site ícone botão cor luz água fogo árvore flor
cachorro gato bolsa sapato óculos relógio mesa cadeira cozinha quarto escritório mercado ônibus avião bicicleta""".split()

STOPWORDS = set("""a o as os de da do das dos e em no na nos nas um uma uns umas para pra por com sem que se ao aos
the of and to in for on with an or""".split())

def fold(text):
 return "".join(c for c in unicodedata.normalize("NFKD", text.lower()) if not unicodedata.combining(c))

def words(text): return [w for w in re.findall(r"\w+", fold(text)) if len(w) > 1 or w.isdigit()]

def content_words(text): return [w for w in words(text) if w not in STOPWORDS] or words(text)

def fts_query(text, prefix=False):
 """Whole words; prefix=True lets the last word be unfinished ("mochi" -> mochila)."""
 tokens = words(text)
 if not tokens: return None
 return " ".join(f'"{t}"' for t in tokens) + ("*" if prefix else "")

def parse(query):
 """'code: retry with backoff' -> ('code', 'retry with backoff')"""
 m = re.match(r"\s*(code|c[oó]digo)\s*:\s*(.*)", query, re.I)
 return ("code", m.group(2).strip()) if m else ("files", query.strip())

def snippet(text, query, width=180):
 text = re.sub(r"\s+", " ", text).strip()
 if len(text) <= width: return text
 folded, at = fold(text), -1
 for w in content_words(query):
  m = re.search(r"(?<!\w)" + re.escape(w), folded)
  if m: at = m.start(); break
 start = max(0, at - width // 3) if at >= 0 else 0
 return ("…" if start else "") + text[start:start + width].strip() + "…"

def home(path):
 h = str(Path.home())
 return "~" + path[len(h):] if path.startswith(h) else path

def clock(sec):
 sec = int(sec or 0)
 return f"{sec // 3600}:{sec % 3600 // 60:02d}:{sec % 60:02d}" if sec >= 3600 else f"{sec // 60}:{sec % 60:02d}"

def location(item):
 k, loc = item["kind"], item.get("loc")
 if loc is None: return ""
 if k == "pdf": return f"Página {loc}"
 if k == "office" and item["path"].lower().endswith((".pptx", ".epub")): return f"Seção {loc}"
 if k == "video": return f"Em {clock(loc)}"
 if k in ("code", "text") and loc > 1: return f"Linha {loc}"
 return ""

def standout(values):
 """z-scores against the median: robust to the handful of relevant items at the top."""
 return (values - np.median(values)) / max(float(values.std()), MIN_SPREAD)

class Searcher:
 def __init__(self, store, embedder, cfg):
  self.store, self.embedder, self.cfg = store, embedder, cfg
  self.semantic_error = None
  self._hub = self._pos = (None, None)
  self._pool = 0

 # ── hubness correction ──
 def _probe_key(self): return "probes:" + hashlib.sha1((self.cfg["model"] + " ".join(PROBES)).encode()).hexdigest()[:12]

 def _probe_vectors(self):
  """Probe embeddings (query and picture caption form), computed once per model and kept in the index."""
  key = self._probe_key()
  blob = self.store.get(key)
  if blob:
   arr = np.frombuffer(base64.b64decode(blob), dtype=np.float16).astype(np.float32)
   return arr.reshape(2, len(PROBES), -1)
  pairs = [self.embedder.query(p, picture=True) for p in PROBES]
  arr = np.stack([np.array([q for q, _ in pairs]), np.array([p for _, p in pairs])])
  self.store.set(key, base64.b64encode(arr.astype(np.float16).tobytes()).decode())
  return arr

 def _hubs(self, scope, ids, mat, mods):
  """Hub value per chunk. Stored in the index: only chunks added since the last search are computed
  (all ~45k at once take seconds with the reference BLAS Arch's numpy uses)."""
  if self._hub[0] is mat: return self._hub[1]
  hub = self.store.hubs(scope).copy()
  todo = np.flatnonzero(np.isnan(hub))
  key = self._probe_key()
  if self.store.get("hub_key") != key: todo = np.arange(len(hub))
  if len(todo):
   try: q, p = self._probe_vectors()
   except EmbedError: return np.zeros(len(mat), np.float32)
   if q.shape[1] != mat.shape[1]: return np.zeros(len(mat), np.float32)
   k = min(HUB_K, len(PROBES))
   for start in range(0, len(todo), 4096):
    rows = todo[start:start + 4096]
    sims = mat[rows] @ np.ascontiguousarray(q.T)
    pictures = np.flatnonzero(mods[rows] == "i")
    if len(pictures): sims[pictures] = mat[rows[pictures]] @ np.ascontiguousarray(p.T)
    hub[rows] = np.partition(sims, -k, axis=1)[:, -k:].mean(1)
   try: self.store.set_hubs(zip(ids[todo].tolist(), hub[todo].tolist()), key)
   except Exception: pass  # read-only or busy index: recomputed next time
  self._hub = (mat, hub)
  return hub

 def warm(self):
  """Load the matrix and hub values and wake the query server, so the first SUPER+D search is quick."""
  ids, mat, mods = self.store.matrix("files", self.cfg["model"])
  if len(ids): self._hubs("files", ids, mat, mods)
  self.embedder.query("warm up")

 # ── scoring ──
 def _semantic(self, scope, query):
  """Text {chunk: z} (best 400) and pictures/sound {chunk: z}, each against its own modality.
  self._z(chunk) gives any text chunk's z, for passages found by exact words."""
  self._z = lambda cid: None
  ids, mat, mods = self.store.matrix(scope, self.cfg["model"])
  if not len(ids): return {}, {}
  pictures = mods == "i"
  try:
   if pictures.any(): qv, pv = self.embedder.query(query, scope, picture=True)
   else: qv = pv = self.embedder.query(query, scope)
   self.semantic_error = None
  except EmbedError as e: self.semantic_error = str(e); return {}, {}
  if mat.shape[1] != len(qv): return {}, {}
  sims = mat @ qv
  if pictures.any(): sims[pictures] = mat[pictures] @ pv
  sims -= self._hubs(scope, ids, mat, mods)
  z = np.full(len(ids), -9.0, np.float32)
  text, media = {}, {}
  for m in ("t", "i", "a"):
   mask = np.flatnonzero(mods == m)
   if not len(mask) or (m != "t" and len(mask) < 20): continue  # too few pictures/sounds to tell what stands out
   z[mask] = standout(sims[mask])
   if m == "t":
    self._pool = len(mask)
    top = mask[np.argsort(-z[mask])[:400]]
    text = {int(ids[i]): float(z[i]) for i in top}
   else: media.update({int(ids[i]): float(z[i]) for i in mask if z[i] >= MEDIA_Z - MEDIA_SPREAD})
  pos = self._positions(ids)
  self._z = lambda cid: float(z[pos[cid]]) if cid in pos and mods[pos[cid]] == "t" else None
  return text, media

 def _positions(self, ids):
  if self._pos[0] is not ids: self._pos = (ids, {int(c): i for i, c in enumerate(ids.tolist())})
  return self._pos[1]

 def _keyword(self, text, scope):
  """({chunk: 0..1}, kind) for passages containing every query word. kind: "rare" (a handful of
  passages: codes, numbers, names), "word", or "prefix" (the last word may be unfinished, tried only
  when the whole word exists nowhere — "mochi" finds mochila, "bota" no longer finds "Botão")."""
  hits, kind = [], None
  for prefix in (False, True):
   match = fts_query(text, prefix)
   if match and (not prefix or len(words(text)[-1]) >= 3): hits = self.store.keyword(match, scope)
   if hits: kind = "prefix" if prefix else ("rare" if len(hits) <= RARE_HITS else "word"); break
  if not hits: return {}, None
  best = min(r for _, r in hits) or -1e-9
  weight = 0.5 if kind == "prefix" else 1.0
  return {cid: weight * (rank / best if best < 0 else 1.0) for cid, rank in hits}, kind

 def search(self, query, limit=30, semantic=True):
  """(scope, results) in display order; r["media"] marks pictures/video/sound, r["copies"] identical files."""
  scope, text = parse(query)
  if not text: return scope, []
  self._z, self._pool = (lambda cid: None), 0
  zs, media = self._semantic(scope, text) if semantic else ({}, {})
  min_z = NOISE_FRACTION * np.sqrt(2 * np.log(max(self._pool, 2)))
  keyword, kind = self._keyword(text, scope)
  # Passages without a vector (tables, data dumps, OCR) only have their words: a rare exact match is as
  # good as a strong semantic one, a common word or a prefix is a weak hint below the semantic results.
  words_only = min_z if not self._pool or kind == "rare" else min_z - KEYWORD_Z * (1.0 if kind == "prefix" else 0.5)
  info = self.store.chunk_info(list(zs) + list(keyword) + list(media))
  qwords = set(content_words(text))
  wants = {m for m, ws in WANTS.items() if qwords & ws}
  counts = self.store.media_counts() if media else {}
  docs, pics = {}, {}
  for cid, c in info.items():
   if cid in media:
    z = media[cid] - MEDIA_MULTI * np.sqrt(2 * np.log(max(counts.get(c["file_id"], 1), 1)))
    best = pics.get(c["file_id"])
    if not best or z > best["score"]: pics[c["file_id"]] = dict(c, score=z, snippet="", media=True)
    continue
   score = zs.get(cid, self._z(cid))
   if score is None: score = words_only
   score += KEYWORD_Z * keyword.get(cid, 0.0)
   name = set(words(os.path.basename(c["path"])))
   if qwords and qwords <= name: score += NAME_Z
   elif qwords & name: score += NAME_Z * len(qwords & name) / len(qwords) / 2
   prev = docs.get(c["file_id"])
   if not prev or score > prev["score"]:
    docs[c["file_id"]] = dict(c, score=score, snippet=snippet(c["text"], text) if c["loc"] is not None else "")
  ranked = sorted(docs.values(), key=lambda r: -r["score"])
  top = ranked[0]["score"] if ranked else 0.0
  ranked = dedupe([r for r in ranked if r["score"] >= min_z and r["score"] >= top - SPREAD_Z])[:limit]
  listed = {r["file_id"] for r in ranked}  # a screenshot found by its text is not repeated as a picture
  shown = dedupe(sorted((r for r in pics.values() if r["file_id"] not in listed), key=lambda r: -r["score"]))
  if wants:  # "foto ...", "música ...": that kind first, and a little less strict
   shown = [r for r in shown if media_kind(r) in wants]
   floor = MEDIA_Z - 0.5
  else: floor = MEDIA_Z
  if shown: shown = [r for r in shown if r["score"] >= floor and r["score"] >= shown[0]["score"] - MEDIA_SPREAD][:MEDIA_LIMIT]
  if wants:  # asked for a kind ("foto de..."): that kind first — found by its text or by how it looks
   kind = [r for r in ranked if media_kind(r) in wants]
   return scope, kind + shown + [r for r in ranked if media_kind(r) not in wants]
  # Otherwise media go where their confidence puts them, but never below the first few documents.
  at = min(sum(r["score"] > shown[0]["score"] for r in ranked), MEDIA_AFTER) if shown else 0
  return scope, ranked[:at] + shown + ranked[at:]

def media_kind(r):
 return {"image": "i", "video": "v", "audio": "a"}.get(r["kind"])

def dedupe(results):
 """One entry per content: copies like 'x.pdf' and 'x (1).pdf' fold into the best-ranked one."""
 out, seen = [], {}
 for r in results:
  key = r.get("digest") or r["path"]
  if key in seen: seen[key]["copies"] = seen[key].get("copies", 0) + 1; continue
  seen[key] = r; out.append(r)
 return out
