"""Hybrid ranking: EmbeddingGemma similarity + boosted exact words + file names, one result per file."""
import os, re, unicodedata
from pathlib import Path
import numpy as np
from embed import EmbedError

# Calibrated on EmbeddingGemma 2 (Q8): text queries score ~0.55 against unrelated text and
# 0.69-0.85 against relevant passages. Images and audio sit in their own ranges, so each
# modality is re-centred on its own median for this query before one threshold applies.
BASELINE = 0.55
MIN_SIMILARITY = 0.64
# Pictures and sound get their own section, ranked by how much an item stands out from the rest of
# its modality (z-score) — a single word like "mochila" rarely beats text containing that word.
MEDIA_Z = 2.5
MEDIA_SPREAD = 1.0  # keep items within this distance of the best one
MEDIA_LIMIT = 4
KEYWORD_WEIGHT = 0.25
NAME_WEIGHT = 0.30

def fold(text):
 return "".join(c for c in unicodedata.normalize("NFKD", text.lower()) if not unicodedata.combining(c))

def words(text): return [w for w in re.findall(r"\w+", fold(text)) if len(w) > 1 or w.isdigit()]

def fts_query(text):
 tokens = words(text)
 if not tokens: return None
 return " ".join(f'"{t}"' for t in tokens[:-1]) + f' "{tokens[-1]}"*'

def parse(query):
 """'code: retry with backoff' -> ('code', 'retry with backoff')"""
 m = re.match(r"\s*(code|c[oó]digo)\s*:\s*(.*)", query, re.I)
 return ("code", m.group(2).strip()) if m else ("files", query.strip())

def snippet(text, query, width=180):
 text = re.sub(r"\s+", " ", text).strip()
 if len(text) <= width: return text
 folded, at = fold(text), -1
 for w in words(query):
  at = folded.find(w)
  if at >= 0: break
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

class Searcher:
 def __init__(self, store, embedder, cfg):
  self.store, self.embedder, self.cfg = store, embedder, cfg
  self.semantic_error = None

 def _semantic(self, scope, query):
  """Text-modality scores {chunk: similarity} and standout media {chunk: z-score}."""
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
  media = {}
  for m in ("i", "a"):
   mask = np.flatnonzero(mods == m)
   if len(mask) < 20: continue  # too few to tell what stands out
   s = sims[mask]; z = (s - np.median(s)) / max(float(s.std()), 1e-6)
   best = float(z.max())
   media.update({int(ids[i]): float(zi) for i, zi in zip(mask, z) if zi >= MEDIA_Z and zi >= best - MEDIA_SPREAD})
   sims[mask] = -1.0  # media never compete in the text ranking
  self._all = dict(zip(ids.tolist(), sims.tolist()))  # true similarity for exact-word hits below the cut
  top = np.argpartition(-sims, min(400, len(sims) - 1))[:400]
  return {int(ids[i]): float(sims[i]) for i in top if sims[i] >= MIN_SIMILARITY}, media

 def search(self, query, limit=30, semantic=True):
  """(scope, results): standout pictures/videos/audio first (r["media"] = True), then documents."""
  scope, text = parse(query)
  if not text: return scope, []
  self._all = {}
  scores, media = self._semantic(scope, text) if semantic else ({}, {})
  match = fts_query(text)
  hits = self.store.keyword(match, scope) if match else []
  if hits:
   best = min(r for _, r in hits) or -1e-9
   for cid, rank in hits:
    base = scores.get(cid, max(self._all.get(cid, BASELINE), BASELINE))
    scores[cid] = base + KEYWORD_WEIGHT * (rank / best if best < 0 else 1.0)
  info = self.store.chunk_info(list(scores) + list(media))
  qwords = set(words(text))
  per_file, media_files = {}, {}
  for cid, z in media.items():
   c = info.get(cid)
   if c and (c["file_id"] not in media_files or z > media_files[c["file_id"]]["z"]):
    media_files[c["file_id"]] = dict(c, z=z, score=BASELINE + 0.05 * z, snippet="", media=True)
  for cid, score in scores.items():
   c = info.get(cid)
   if not c or c["file_id"] in media_files: continue
   name = set(words(c["path"].rsplit("/", 1)[-1]))
   if qwords and qwords <= name: score += NAME_WEIGHT
   elif qwords & name: score += NAME_WEIGHT * len(qwords & name) / len(qwords) / 2
   prev = per_file.get(c["file_id"])
   if not prev or score > prev["score"]: per_file[c["file_id"]] = dict(c, score=score, snippet=snippet(c["text"], text) if c["loc"] is not None else "")
  shown = sorted(media_files.values(), key=lambda r: -r["z"])[:MEDIA_LIMIT]
  return scope, shown + sorted(per_file.values(), key=lambda r: -r["score"])[:limit]
