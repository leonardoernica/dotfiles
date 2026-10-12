#!/usr/bin/env python3
"""Garimpo: describe it, dig it up. Local semantic search for Hyprland, inspired by DigUp.

  garimpo                    open/close the palette (SUPER+D)
  garimpo open TEXT          open the palette already searching for TEXT
  garimpo ui --hidden        start the resident palette without showing it
  garimpo index [--watch]    index the configured folders (once, or continuously)
  garimpo search TEXT        search from the terminal (prefix with code: for code)
  garimpo status | doctor    index state / dependency check
  garimpo setup              download the pinned llama.cpp + EmbeddingGemma 2 (SHA-256 checked)
  garimpo serve [--query]    run the local embedding server (garimpo-embed / garimpo-query services)
  garimpo pause | resume     pause or resume background indexing
"""
import argparse, json, os, shutil, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import config

def open_store():
 from store import Store
 return Store(config.STATE / "index.db")

def cmd_index(args, cfg):
 from embed import Embedder
 from indexer import Indexer
 idx = Indexer(cfg, open_store(), Embedder(cfg), log=lambda m: print(m, flush=True))
 if args.watch: idx.watch()
 else: idx.cycle()

def cmd_search(args, cfg):
 from embed import Embedder
 import search
 searcher = search.Searcher(open_store(), Embedder(cfg), cfg)
 started = time.perf_counter()
 scope, results = searcher.search(" ".join(args.text), limit=args.limit)
 if searcher.semantic_error: print(f"(sem busca semântica: {searcher.semantic_error})", file=sys.stderr)
 for r in results:
  where = search.location(r)
  tag = f"mídia z={r['z']:.1f}" if r.get("media") else f"{r['score']:.3f}"
  print(f"{tag}  {search.home(r['path'])}" + (f"  [{where}]" if where else ""))
  if r.get("snippet"): print(f"       {r['snippet'][:140]}")
 print(f"{len(results)} resultados em {time.perf_counter() - started:.2f}s ({scope})", file=sys.stderr)

def cmd_open(args, cfg):
 from gi.repository import Gio, GLib
 Gio.bus_get_sync(Gio.BusType.SESSION).call_sync(config.APP_ID, "/" + config.APP_ID.replace(".", "/"), "org.freedesktop.Application",
  "ActivateAction", GLib.Variant("(sava{sv})", ("search", [GLib.Variant("s", " ".join(args.text))], {})), None, Gio.DBusCallFlags.NONE, 3000)

def cmd_status(args, cfg):
 store = open_store()
 print(json.dumps(dict(store.stats(), status=json.loads(store.get("status") or "{}"), paused=(config.STATE / "paused").exists()), indent=1, ensure_ascii=False))

def cmd_doctor(args, cfg):
 from embed import Embedder
 import readers
 import runtime
 ok, msg = Embedder(cfg).status()
 checks = [("llama.cpp " + config.LLAMA_BUILD, (runtime.llama_dir() / "llama-server").exists(), str(runtime.llama_dir())),
           ("modelos", all((config.MODELS / n).exists() for n in config.MODEL_FILES), str(config.MODELS)),
           ("servidor de embeddings", ok, msg)]
 try:
  Embedder(cfg)._request("/health", timeout=3, url=cfg["query_server"])
  checks.append(("servidor de consultas", True, cfg["query_server"]))
 except Exception as e: checks.append(("servidor de consultas", False, f"{e} (systemctl --user status garimpo-query)"))
 for tool, why in (("pdftotext", "texto de PDFs (poppler)"), ("tesseract", "OCR de capturas e PDFs escaneados"),
                   ("ffmpeg", "frames de vídeo"), ("wl-copy", "copiar arquivos"), ("busctl", "abertura instantânea")):
  checks.append((tool, bool(shutil.which(tool)), why))
 langs = readers.ocr_langs()
 checks.append(("OCR em português", bool(langs and "por" in langs), langs or "sem tesseract"))
 for name, good, detail in checks: print(f"{'✓' if good else '✗'} {name}: {detail}")
 print(f"  config: {config.CONFIG_FILE}{'' if config.CONFIG_FILE.exists() else ' (padrões)'}")
 print(f"  índice: {config.STATE / 'index.db'}")

def main():
 parser = argparse.ArgumentParser(prog="garimpo", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
 sub = parser.add_subparsers(dest="cmd")
 p = sub.add_parser("ui"); p.add_argument("--hidden", action="store_true")
 p = sub.add_parser("index"); p.add_argument("--watch", action="store_true")
 p = sub.add_parser("open"); p.add_argument("text", nargs="+")
 p = sub.add_parser("search"); p.add_argument("text", nargs="+"); p.add_argument("-n", "--limit", type=int, default=15)
 p = sub.add_parser("serve"); p.add_argument("--query", action="store_true")
 for name in ("status", "doctor", "pause", "resume", "setup"): sub.add_parser(name)
 args = parser.parse_args()
 cfg = config.load()
 if args.cmd in (None, "ui"):
  import ui
  return ui.main(hidden=getattr(args, "hidden", False))
 if args.cmd in ("setup", "serve"):
  import runtime
  return runtime.setup() if args.cmd == "setup" else runtime.serve(cfg, query=args.query)
 if args.cmd == "pause": config.STATE.mkdir(parents=True, exist_ok=True); (config.STATE / "paused").touch(); return
 if args.cmd == "resume": (config.STATE / "paused").unlink(missing_ok=True); return
 {"open": cmd_open, "index": cmd_index, "search": cmd_search, "status": cmd_status, "doctor": cmd_doctor}[args.cmd](args, cfg)

if __name__ == "__main__":
 sys.exit(main())
