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
 "ollama": "http://localhost:11434",
 "model": "embeddinggemma-2:440m",
 "dimensions": 768,
 "images": True,
 "videos": True,
 "ocr": True,
 "pdf_first_pages": 30,
 "pdf_max_pages": 2000,
 "video_max_frames": 40,
 "pause_on_battery": False,
 "rescan_seconds": 120,
 "editor": "code",
}

def load(path=CONFIG_FILE):
 cfg = dict(DEFAULTS)
 if path.exists():
  with open(path, "rb") as f: cfg.update(tomllib.load(f))
 for key in ("roots", "code_roots"): cfg[key] = [Path(os.path.expanduser(p)) for p in cfg[key]]
 return cfg
