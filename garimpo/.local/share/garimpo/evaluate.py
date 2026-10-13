"""Ranking evaluation: run known searches and measure where the expected files land.

Cases live outside the repository (they name personal files), in ~/.local/state/garimpo/eval.json:
  [{"q": "contrato de aluguel", "want": ["Contrato_Locacao", "CTR APTO"]},   # any of these path fragments
   {"q": "receita de bolo", "want": []}]                                      # nothing relevant exists
"""
import json, os, re, time
import config, search

def run(searcher, cases, verbose=False, log=print):
 rr, top1, top5, noise, dupes, slow = [], 0, 0, [], 0, 0.0
 for case in cases:
  started = time.perf_counter()
  _, results = searcher.search(case["q"], limit=30)
  slow = max(slow, time.perf_counter() - started)
  paths = [r["path"] for r in results]
  names = [re.sub(r" \(\d+\)", "", os.path.basename(p)).lower() for p in paths[:10]]
  dupes += len(names) - len(set(names))  # copies like "x.pdf", "x (1).pdf" in the first ten
  want = [w.lower() for w in case["want"]]
  if not want:
   noise.append(len(results))
   if verbose: log(f"  {len(results):2d} resultados   {case['q']!r} (nada deveria aparecer)" + "".join(f"\n      {search.home(p)}" for p in paths[:3]))
   continue
  rank = next((i for i, p in enumerate(paths, 1) if any(w in p.lower() for w in want)), None)
  rr.append(1 / rank if rank and rank <= 10 else 0.0)
  top1 += rank == 1; top5 += bool(rank and rank <= 5)
  if verbose:
   log(f"  {'·' if rank == 1 else (rank or '—')!s:>2}  {case['q']!r}" + ("" if rank == 1 else "".join(f"\n      {search.home(p)}" for p in paths[:3])))
 n = len(rr)
 summary = dict(cases=n, mrr=round(sum(rr) / max(n, 1), 3), top1=f"{top1}/{n}", top5=f"{top5}/{n}",
                noise=round(sum(noise) / max(len(noise), 1), 1), duplicates=dupes, slowest=f"{slow:.2f}s")
 log(json.dumps(summary, ensure_ascii=False))
 return summary

def load(path=None):
 return json.loads((path or config.STATE / "eval.json").read_text())
