"""Install and run the pinned llama.cpp server with EmbeddingGemma 2. No root needed: ~/.local/opt and ~/.cache."""
import hashlib, os, shutil, subprocess, sys, tarfile, tempfile, urllib.request
from pathlib import Path
import config

def llama_dir(): return config.OPT / f"llama-{config.LLAMA_BUILD}"

def sha256(path):
 h = hashlib.sha256()
 with open(path, "rb") as f:
  for block in iter(lambda: f.read(1 << 20), b""): h.update(block)
 return h.hexdigest()

def download(url, dest, digest, log):
 """Download to a temporary file, check SHA-256, then move into place."""
 dest.parent.mkdir(parents=True, exist_ok=True)
 tmp = dest.with_suffix(dest.suffix + ".part")
 log(f"  baixando {url.rsplit('/', 1)[-1]}…")
 with urllib.request.urlopen(url, timeout=60) as r, open(tmp, "wb") as f: shutil.copyfileobj(r, f, 1 << 20)
 if sha256(tmp) != digest:
  tmp.unlink(); raise SystemExit(f"SHA-256 inválido para {url}; nada foi instalado")
 tmp.replace(dest)

def setup(log=print):
 """Fetch the pinned llama.cpp build and model files (skipping what is already valid)."""
 target = llama_dir()
 if not (target / "llama-server").exists():
  with tempfile.TemporaryDirectory() as tmp:
   archive = Path(tmp) / "llama.tar.gz"
   download(config.LLAMA_URL, archive, config.LLAMA_SHA256, log)
   with tarfile.open(archive) as t: t.extractall(config.OPT, filter="data")
  log(f"✓ llama.cpp {config.LLAMA_BUILD} em {target}")
 else: log(f"✓ llama.cpp {config.LLAMA_BUILD} já instalado")
 for name, digest in config.MODEL_FILES.items():
  path = config.MODELS / name
  if path.exists() and sha256(path) == digest: log(f"✓ {name}"); continue
  download(config.MODEL_URL + name, path, digest, log); log(f"✓ {name}")

def serve(cfg, query=False):
 """exec llama-server bound to localhost, embeddings only.

 The indexing server loads the vision/audio encoders; the query server is text-only and
 never waits behind indexing batches, so SUPER+D stays fast. Weights are memory-mapped
 from the same file, so the second process costs little memory."""
 binary = llama_dir() / "llama-server"
 if not binary.exists(): raise SystemExit("llama.cpp ausente: rode `garimpo setup`")
 model, mmproj = (config.MODELS / n for n in config.MODEL_FILES)
 host, port = cfg["query_server" if query else "server"].split("//", 1)[1].rsplit(":", 1)
 threads = cfg["threads"] or max(2, (os.cpu_count() or 4) // 2)
 argv = [str(binary), "-m", str(model), "--embedding", "--host", host, "--port", port.strip("/"), "--no-webui",
         "--cache-ram", "0", "-ngl", "0", "--alias", cfg["model"]]
 if query: argv += ["-c", "1024", "-b", "1024", "-ub", "1024", "-np", "1", "-t", str(min(threads, 4))]
 else: argv += ["--mmproj", str(mmproj), "-c", "8192", "-b", "2048", "-ub", "2048", "-np", "4", "-t", str(threads)]
 sys.stdout.flush()
 os.execv(argv[0], argv)
