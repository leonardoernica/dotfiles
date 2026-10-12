"""Hybrid ranking: EmbeddingGemma similarity + boosted exact words + file names, one result per file."""
import os, re, unicodedata
from pathlib import Path
import numpy as np
from embed import EmbedError

MIN_SIMILARITY = 0.30
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
  ids, mat = self.store.matrix(scope, self.cfg["model"])
  if not len(ids): return {}
  try: qv = self.embedder.query(query); self.semantic_error = None
  except EmbedError as e: self.semantic_error = str(e); return {}
  if mat.shape[1] != len(qv): return {}
  sims = mat @ qv
  top = np.argpartition(-sims, min(400, len(sims) - 1))[:400]
  return {int(ids[i]): float(sims[i]) for i in top if sims[i] >= MIN_SIMILARITY}

 def search(self, query, limit=30, semantic=True):
  scope, text = parse(query)
  if not text: return scope, []
  scores = self._semantic(scope, text) if semantic else {}
  match = fts_query(text)
  hits = self.store.keyword(match, scope) if match else []
  if hits:
   best = min(r for _, r in hits) or -1e-9
   for cid, rank in hits: scores[cid] = scores.get(cid, 0.0) + KEYWORD_WEIGHT * (rank / best if best < 0 else 1.0)
  info = self.store.chunk_info(list(scores))
  qwords = set(words(text))
  per_file = {}
  for cid, score in scores.items():
   c = info.get(cid)
   if not c: continue
   name = set(words(c["path"].rsplit("/", 1)[-1]))
   if qwords and qwords <= name: score += NAME_WEIGHT
   elif qwords & name: score += NAME_WEIGHT * len(qwords & name) / len(qwords) / 2
   prev = per_file.get(c["file_id"])
   if not prev or score > prev["score"]: per_file[c["file_id"]] = dict(c, score=score, snippet=snippet(c["text"], text) if c["loc"] is not None else "")
  return scope, sorted(per_file.values(), key=lambda r: -r["score"])[:limit]
