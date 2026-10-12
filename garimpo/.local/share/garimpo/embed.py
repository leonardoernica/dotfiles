"""EmbeddingGemma 2 (text, image and audio in one space) through a local llama.cpp server.

Nothing leaves the machine: the server listens on 127.0.0.1 and is started by garimpo-embed.service."""
import base64, json, urllib.error, urllib.request
import numpy as np

# Task prefixes from the model card; images and audio take no prefix.
QUERY = {"files": "task: search result | query: {}", "code": "task: code retrieval | query: {}"}
DOCUMENT = "title: {} | text: {}"

class EmbedError(Exception):
 def __init__(self, message, offline=False): super().__init__(message); self.offline = offline

class Embedder:
 def __init__(self, cfg):
  self.url, self.dims = cfg["server"].rstrip("/"), cfg["dimensions"]
  self.query_url = cfg.get("query_server", "").rstrip("/")
  self.marker, self.modalities = None, {}
  self.images = None  # kept for the indexer: False when the server cannot embed images

 def _request(self, path, body=None, timeout=300, url=None):
  data = None if body is None else json.dumps(body).encode()
  req = urllib.request.Request((url or self.url) + path, data, {"Content-Type": "application/json"})
  try:
   with urllib.request.urlopen(req, timeout=timeout) as r: return json.load(r)
  except urllib.error.HTTPError as e:
   raise EmbedError(e.read().decode(errors="replace")[:300] or str(e), offline=e.code == 503) from e
  except (urllib.error.URLError, OSError) as e:
   raise EmbedError(f"servidor de embeddings indisponível em {self.url}: {e}", offline=True) from e

 def _props(self):
  """The media marker is random per server start, so it is re-read after a restart."""
  props = self._request("/props", timeout=5)
  self.marker, self.modalities = props.get("media_marker"), props.get("modalities", {})
  self.images = bool(self.marker and self.modalities.get("vision"))
  return props

 def status(self):
  """(ok, message) — cheap, does not run the model."""
  try: props = self._props()
  except EmbedError as e: return False, f"{e} (systemctl --user status garimpo-embed)"
  name = props.get("model_alias") or props.get("model_path", "").rsplit("/", 1)[-1]
  kinds = "+".join(k for k in ("vision", "audio") if self.modalities.get(k))
  return True, f"{name} ({'texto+' + kinds if kinds else 'só texto'})"

 def _embed(self, inputs, timeout=300, url=None):
  data = self._request("/v1/embeddings", {"input": inputs}, timeout, url)["data"]
  vecs = np.asarray([d["embedding"] for d in sorted(data, key=lambda d: d["index"])], dtype=np.float32)
  if vecs.ndim != 2 or len(vecs) != len(inputs): raise EmbedError("resposta inesperada do servidor")
  vecs = vecs[:, :self.dims]  # Matryoshka: leading dimensions, then re-normalize
  return vecs / np.maximum(np.linalg.norm(vecs, axis=1, keepdims=True), 1e-9)

 def query(self, text, scope="files"):
  prompt = [QUERY.get(scope, QUERY["files"]).format(text)]
  if self.query_url:
   try: return self._embed(prompt, timeout=10, url=self.query_url)[0]
   except EmbedError: pass  # query server down: fall back to the indexing server
  return self._embed(prompt, timeout=30)[0]

 def documents(self, pairs):
  """pairs: [(title, text)] -> normalized matrix."""
  return self._embed([DOCUMENT.format(t or "none", x) for t, x in pairs])

 def _media(self, payload, modality):
  if self.marker is None: self._props()
  if not self.modalities.get(modality): return None
  item = lambda: {"prompt_string": self.marker, "multimodal_data": [base64.b64encode(payload).decode()]}
  try: return self._embed([item()])[0]
  except EmbedError as e:
   if e.offline: raise
   self._props()  # the server may have restarted with a new marker
   return self._embed([item()])[0]

 def image(self, jpeg_bytes): return self._media(jpeg_bytes, "vision")
 def audio(self, wav_bytes): return self._media(wav_bytes, "audio")
