"""EmbeddingGemma 2 through the local Ollama server. Nothing leaves the machine."""
import base64, json, urllib.error, urllib.request
import numpy as np

QUERY = "task: search result | query: {}"
DOCUMENT = "title: {} | text: {}"

class EmbedError(Exception):
 def __init__(self, message, offline=False): super().__init__(message); self.offline = offline

class Embedder:
 def __init__(self, cfg):
  self.url, self.model, self.dims = cfg["ollama"].rstrip("/"), cfg["model"], cfg["dimensions"]
  self.images = None  # unknown until the first image request answers

 def _post(self, path, body, timeout=120):
  req = urllib.request.Request(self.url + path, json.dumps(body).encode(), {"Content-Type": "application/json"})
  try:
   with urllib.request.urlopen(req, timeout=timeout) as r: return json.load(r)
  except urllib.error.HTTPError as e:
   raise EmbedError(e.read().decode(errors="replace")[:300] or str(e)) from e
  except (urllib.error.URLError, OSError) as e:
   raise EmbedError(f"Ollama indisponível em {self.url}: {e}", offline=True) from e

 def status(self):
  """Return (ok, message) without loading the model."""
  try:
   with urllib.request.urlopen(self.url + "/api/tags", timeout=2) as r: names = [m["name"] for m in json.load(r)["models"]]
  except (urllib.error.URLError, OSError, ValueError) as e: return False, f"Ollama indisponível: {e}"
  wanted = self.model if ":" in self.model else self.model + ":latest"
  if wanted not in names: return False, f"Modelo ausente: ollama pull {self.model}"
  return True, self.model

 def _embed(self, inputs, timeout=300):
  data = self._post("/api/embed", {"model": self.model, "input": inputs, "dimensions": self.dims, "keep_alive": "30m"}, timeout)
  vecs = np.asarray(data["embeddings"], dtype=np.float32)
  if vecs.ndim != 2 or len(vecs) != len(inputs): raise EmbedError("Resposta inesperada do Ollama")
  return vecs / np.maximum(np.linalg.norm(vecs, axis=1, keepdims=True), 1e-9)

 def query(self, text): return self._embed([QUERY.format(text)], timeout=30)[0]

 def documents(self, pairs):
  """pairs: [(title, text)] -> normalized matrix."""
  return self._embed([DOCUMENT.format(t or "none", x) for t, x in pairs])

 def image(self, jpeg_bytes):
  """Embed raw image bytes in the shared text/image space; None if the model or server cannot."""
  if self.images is False: return None
  try: vec = self._embed([{"image": base64.b64encode(jpeg_bytes).decode()}])[0]
  except EmbedError as e:
   if e.offline: raise
   if self.images is None: self.images = False
   return None
  self.images = True
  return vec
