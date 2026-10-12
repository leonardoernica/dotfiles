"""Garimpo settings: defaults merged with ~/.config/garimpo/config.toml."""
import os, tomllib
from pathlib import Path

HOME = Path.home()
CONFIG_FILE = Path(os.environ.get("XDG_CONFIG_HOME", HOME / ".config")) / "garimpo" / "config.toml"
STATE = Path(os.environ.get("XDG_STATE_HOME", HOME / ".local/state")) / "garimpo"
CACHE = Path(os.environ.get("XDG_CACHE_HOME", HOME / ".cache")) / "garimpo"
APP_ID = "io.github.leonardoernica.Garimpo"

DEFAULTS = {
 "roots": ["~/Documents", "~/Documentos", "~/Downloads", "~/Imagens", "~/Pictures", "~/Área de trabalho",
           "~/Desktop", "~/Vídeos", "~/Videos", "~/Músicas", "~/Music", "~/study"],
 # Code search is opt-in, like DigUp: add project folders here and use the "code:" prefix.
 "code_roots": [],
 "exclude": [],
 # Local llama.cpp server (garimpo-embed.service). "model" tags the vectors: changing it re-embeds.
 "server": "http://127.0.0.1:8765",
 "query_server": "http://127.0.0.1:8766",  # text-only twin for searches (garimpo-query.service)
 "model": "embeddinggemma-2-Q8_0",
 "dimensions": 768,
 "threads": 0,  # llama.cpp threads; 0 = half of the CPU cores, leaving room for the desktop
 "images": True,
 "videos": True,
 "audio": True,
 "audio_max_windows": 120,
 "ocr": True,
 "pdf_first_pages": 30,
 "pdf_max_pages": 2000,
 "video_max_frames": 40,
 "pause_on_battery": False,
 "rescan_seconds": 600,  # safety net: inotify picks up changes within seconds
 "editor": "code",
}

# Pinned runtime and model, as DigUp ships them: llama.cpp + ggml-org's 8-bit EmbeddingGemma 2 build.
OPT = HOME / ".local/opt/llama-cpp"
LLAMA_BUILD = "b11574"
LLAMA_URL = f"https://github.com/ggml-org/llama.cpp/releases/download/{LLAMA_BUILD}/llama-{LLAMA_BUILD}-bin-ubuntu-vulkan-x64.tar.gz"
LLAMA_SHA256 = "405600a8e6073525d202e3e7aad14929501f317de4c9687d16cc6e2bc0eed49d"
MODELS = CACHE / "models"
MODEL_URL = "https://huggingface.co/ggml-org/embeddinggemma-2-GGUF/resolve/main/"
MODEL_FILES = {  # text model (310 MB) + vision/audio encoders (555 MB)
 "embeddinggemma-2-Q8_0.gguf": "2188ac1deca4b77dffefd603c2776a9d76d9d74ec01841392982ebb840b09135",
 "mmproj-embeddinggemma-2-Q8_0.gguf": "c4a8a52691ecef40618438928bdf9e68379b854e24166f292592353db0aab64f",
}

def load(path=CONFIG_FILE):
 cfg = dict(DEFAULTS)
 if path.exists():
  with open(path, "rb") as f: cfg.update(tomllib.load(f))
 for key in ("roots", "code_roots"): cfg[key] = [Path(os.path.expanduser(p)) for p in cfg[key]]
 if cfg["dimensions"] != 768: cfg["model"] += f"-d{cfg['dimensions']}"  # vectors of another size: re-embed
 return cfg
