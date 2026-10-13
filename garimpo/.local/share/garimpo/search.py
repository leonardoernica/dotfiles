"""Hybrid ranking: EmbeddingGemma similarity + exact words + file names, one result per file.

Every signal is put on one scale: how many standard deviations a piece stands out from the rest of
its kind (text, pictures, sound) *for this query*. Raw cosine similarities drift from query to query
(a common word lifts thousands of chunks), so a fixed cut-off let in hundreds of results for some
searches and nothing for others. Measured with `garimpo eval`."""
import base64, bisect, hashlib, os, re, time, unicodedata
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
APP_Z = 3.0        # applications by meaning: "xadrez" finds Chess Overlay, "planilha" LibreOffice Calc
APP_LIMIT = 3
FOLDER_Z = 1.5     # query words in the folder names: preview.png inside chess-overlay/ is about chess
TYPO_MIN = 4       # words this long tolerate a typo (8+ letters: two)
VOCAB_SECONDS = 120  # the word list follows the index, at most this often
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

def typo_distance(a, b, limit):
 """Edit distance with swapped neighbours counted once (croassant/croissant: 1, xadrze/xadrez: 1),
 or limit + 1 as soon as it is clearly larger."""
 if abs(len(a) - len(b)) > limit: return limit + 1
 prev2, prev = None, list(range(len(b) + 1))
 for i, ca in enumerate(a, 1):
  cur = [i] + [0] * len(b)
  for j, cb in enumerate(b, 1):
   cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb))
   if prev2 and i > 1 and j > 1 and ca == b[j - 2] and a[i - 2] == cb: cur[j] = min(cur[j], prev2[j - 2] + 1)
  if min(cur) > limit: return limit + 1
  prev2, prev = prev, cur
 return prev[-1]

def letters(word):
 bits = 0
 for ch in word: bits |= 1 << (ord(ch) % 64)
 return bits

def allowed_typos(word): return 0 if len(word) < TYPO_MIN else 1 if len(word) < 8 else 2

class Vocabulary:
 """Every word the index (and the app list) knows, to fix typos before searching."""
 def __init__(self, counts):
  self.counts, self.sorted = counts, sorted(counts)
  # (length, letter) -> [(letters bitmask, word)]: a typo rarely hits both first letters, and each
  # edit changes at most two letters of the set, so most candidates fail a cheap XOR before the real distance.
  self.first, self.second = {}, {}
  for w in self.sorted:
   entry = (letters(w), w)
   self.first.setdefault((len(w), w[0]), []).append(entry)
   if len(w) > 1: self.second.setdefault((len(w), w[1]), []).append(entry)

 def known(self, word): return word in self.counts

 def started(self, word):
  """Some known word begins with it: probably still being typed."""
  i = bisect.bisect_left(self.sorted, word)
  return i < len(self.sorted) and self.sorted[i].startswith(word)

 def closest(self, word, keep=3):
  """Known words at the smallest distance, most frequent first (several when it is a tie:
  "pultao" is one letter from both plutao and pulmao — the ranking, not the spelling, decides)."""
  limit = allowed_typos(word)
  if not limit or word.isdigit(): return []
  found, mask = [], letters(word)
  for n in range(len(word) - limit, len(word) + limit + 1):
   for bits, cand in (*self.first.get((n, word[0]), ()), *self.second.get((n, word[1]), ())):
    if (bits ^ mask).bit_count() > 2 * limit: continue
    d = typo_distance(word, cand, limit)
    if d <= limit: found.append((d, -self.counts[cand], cand))
  found = sorted(set(found))  # a word can sit in both buckets
  return [c for d, _, c in found if d == found[0][0]][:keep]

 def fix(self, text):
  """{typed: [known spellings]} for words no file or app contains (and that are not being typed)."""
  fixes = {}
  for w in words(text):
   if w not in fixes and not self.known(w) and not self.started(w) and (c := self.closest(w)): fixes[w] = c
  return fixes

def respell(text, fixes, k):
 """text with each misspelled word replaced by its k-th fix (or its last one)."""
 def swap(m):
  alts = fixes.get(fold(m.group()))
  return alts[min(k, len(alts) - 1)] if alts else m.group()
 return re.sub(r"\w+", swap, text)

def fts_query(text, prefix=False, alternatives=None):
 """Whole words; prefix=True lets the last word be unfinished ("mochi" -> mochila);
 alternatives {typed: fixed} accept either spelling."""
 tokens = words(text)
 if not tokens: return None
 alternatives = alternatives or {}
 term = lambda t: "(" + " OR ".join(f'"{a}"' for a in [t, *alternatives[t]]) + ")" if t in alternatives else f'"{t}"'
 return " ".join(term(t) for t in tokens[:-1]) + " " + (f'"{tokens[-1]}"*' if prefix else term(tokens[-1]))

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
  self._qvs, self._apps = [], {}
  self._vocab, self.extra_words, self.fixes = (None, None, 0.0, -1), set(), {}
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
  self.vocabulary()
  self.embedder.query("warm up")

 # ── scoring ──
 def _semantic(self, scope, query, variants=()):
  """Text {chunk: z} (best 400) and pictures/sound {chunk: z}, each against its own modality.
  self._z(chunk) gives any text chunk's z, for passages found by exact words."""
  self._z = lambda cid: None
  ids, mat, mods = self.store.matrix(scope, self.cfg["model"])
  if not len(ids): return {}, {}
  pictures = mods == "i"
  try:  # the query as typed and its spelling fixes: each passage keeps its best match
   vecs = [self.embedder.query(q, scope, picture=True) if pictures.any() else (self.embedder.query(q, scope),) * 2
           for q in (query, *variants)]
   self.semantic_error = None
  except EmbedError as e: self.semantic_error = str(e); return {}, {}
  self._qvs = [qv for qv, _ in vecs]
  if mat.shape[1] != len(vecs[0][0]): return {}, {}
  hubs = self._hubs(scope, ids, mat, mods)
  z = np.full(len(ids), -9.0, np.float32)
  masks = {m: np.flatnonzero(mods == m) for m in ("t", "i", "a")}
  for qv, pv in vecs:  # each spelling on its own scale, then the best: a misspelling is noise, not signal
   sims = mat @ qv
   if pictures.any(): sims[pictures] = mat[pictures] @ pv
   sims -= hubs
   for m, mask in masks.items():
    if len(mask) and (m == "t" or len(mask) >= 20): z[mask] = np.maximum(z[mask], standout(sims[mask]))
  text, media = {}, {}
  for m, mask in masks.items():
   if not len(mask) or (m != "t" and len(mask) < 20): continue  # too few pictures/sounds to tell what stands out
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

 def _keyword(self, text, scope, alternatives=None):
  """({chunk: 0..1}, kind) for passages containing every query word. kind: "rare" (a handful of
  passages: codes, numbers, names), "word", or "prefix" (the last word may be unfinished, tried only
  when the whole word exists nowhere — "mochi" finds mochila, "bota" no longer finds "Botão")."""
  hits, kind = [], None
  for prefix in (False, True):
   match = fts_query(text, prefix, alternatives)
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
  # Typos: a word no file or app contains is searched as typed *and* as its closest known spellings
  # (croassant -> croissant). Searching both, not replacing, keeps "gato" intact when no text has it:
  # the photo of a cat still matches "gato", whatever the spelling fix ("gado") brings.
  self.fixes = fixes = self.vocabulary().fix(text)
  variants = [respell(text, fixes, k) for k in range(max((len(a) for a in fixes.values()), default=0))]
  self._z, self._pool, self._qvs = (lambda cid: None), 0, []
  zs, media = self._semantic(scope, text, variants) if semantic else ({}, {})
  min_z = NOISE_FRACTION * np.sqrt(2 * np.log(max(self._pool, 2)))
  keyword, kind = self._keyword(text, scope, fixes)
  # Passages without a vector (tables, data dumps, OCR) only have their words: a rare exact match is as
  # good as a strong semantic one, a common word or a prefix is a weak hint below the semantic results.
  words_only = min_z if not self._pool or kind == "rare" else min_z - KEYWORD_Z * (1.0 if kind == "prefix" else 0.5)
  info = self.store.chunk_info(list(zs) + list(keyword) + list(media))
  groups = [{w, *fixes.get(w, ())} for w in content_words(text)]  # each typed word, or one of its fixes
  qwords = set().union(*groups)
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
   in_name = sum(bool(g & name) for g in groups)
   if groups and in_name == len(groups): score += NAME_Z
   elif in_name: score += NAME_Z * in_name / len(groups) / 2
   folders = set(words(" ".join(c["path"].split("/")[-4:-1]))) - name
   in_folder = sum(bool(g & folders) and not g & name for g in groups)
   if in_folder: score += FOLDER_Z * in_folder / len(groups)
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

 def vocabulary(self):
  vocab, gen, at, size = self._vocab
  if vocab is None or len(self.extra_words) != size or (self.store.generation() != gen and time.time() - at > VOCAB_SECONDS):
   counts = self.store.vocabulary()
   for w in self.extra_words: counts.setdefault(w, 1)
   self._vocab = (Vocabulary(counts), self.store.generation(), time.time(), len(self.extra_words))
  return self._vocab[0]

 # ── applications ──
 def app_hits(self, apps, query=None):
  """apps: [(app_id, name, text)] -> [(app_id, z)] for apps that match the last query by meaning.
  App vectors are computed once on the query server and kept in the index."""
  if query is not None and not self._qvs:
   try: self._qvs = [self.embedder.query(parse(query)[1])]
   except EmbedError: return []
  if not self._qvs or not apps: return []
  key = lambda a: "app:" + hashlib.sha1((self.cfg["model"] + a[1] + a[2]).encode()).hexdigest()[:16]
  missing = [a for a in apps if key(a) not in self._apps]
  stored = {a: self.store.get(key(a)) for a in missing}
  for a, blob in stored.items():
   if blob: self._apps[key(a)] = np.frombuffer(base64.b64decode(blob), dtype=np.float16).astype(np.float32)
  todo = [a for a in missing if key(a) not in self._apps]
  for i in range(0, len(todo), 16):
   batch = todo[i:i + 16]
   try: vecs = self.embedder.documents([(name, text) for _, name, text in batch], quick=True)
   except EmbedError: return []
   for a, v in zip(batch, vecs):
    self._apps[key(a)] = v
    self.store.set(key(a), base64.b64encode(np.asarray(v, np.float16).tobytes()).decode())
  mat = np.stack([self._apps[key(a)] for a in apps])
  if mat.shape[1] != len(self._qvs[0]): return []
  z = standout(np.max([mat @ qv for qv in self._qvs], axis=0))
  best = sorted(((float(zi), a[0]) for zi, a in zip(z, apps) if zi >= APP_Z), reverse=True)[:APP_LIMIT]
  return [(app_id, zi) for zi, app_id in best if zi >= best[0][0] - 1.0]

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
