"""Ranking evaluation: run known searches and measure where the expected files land.

Your own searches count automatically: every time you open a file from the palette, the query and the
file go to ~/.local/state/garimpo/searches.jsonl. Extra cases, outside the repository (they name
personal files), go in ~/.local/state/garimpo/eval.json:
  [{"q": "contrato de aluguel", "want": ["Contrato_Locacao", "CTR APTO"]},   # any of these path fragments
   {"q": "receita de bolo", "want": []},                                     # nothing relevant exists
   {"q": "boleto", "want": ["boleto"], "media": false}]                       # pictures/sound here are noise
"""
import json, os, random, re, time
import config, search

def run(searcher, cases, verbose=False, log=print):
 rr, top1, top5, noise, dupes, slow, stray = [], 0, 0, [], 0, 0.0, 0
 for case in cases:
  started = time.perf_counter()
  _, results = searcher.search(case["q"], limit=30)
  slow = max(slow, time.perf_counter() - started)
  paths = [r["path"] for r in results]
  names = [re.sub(r" \(\d+\)", "", os.path.basename(p)).lower() for p in paths[:10]]
  dupes += len(names) - len(set(names))  # copies like "x.pdf", "x (1).pdf" in the first ten
  if case.get("media") is False: stray += sum(bool(r.get("media")) for r in results)
  want = [search.fold(w) for w in case["want"]]  # file names may be NFD: compare folded
  if not want:
   noise.append(len(results))
   if verbose: log(f"  {len(results):2d} resultados   {case['q']!r} (nada deveria aparecer)" + "".join(f"\n      {search.home(p)}" for p in paths[:3]))
   continue
  rank = next((i for i, p in enumerate(paths, 1) if any(w in search.fold(p) for w in want)), None)
  rr.append(1 / rank if rank and rank <= 10 else 0.0)
  top1 += rank == 1; top5 += bool(rank and rank <= 5)
  if verbose:
   log(f"  {'·' if rank == 1 else (rank or '—')!s:>2}  {case['q']!r}" + ("" if rank == 1 else "".join(f"\n      {search.home(p)}" for p in paths[:3])))
 n = len(rr)
 summary = dict(cases=n, mrr=round(sum(rr) / max(n, 1), 3), top1=f"{top1}/{n}", top5=f"{top5}/{n}",
                noise=round(sum(noise) / max(len(noise), 1), 1), stray_media=stray, duplicates=dupes, slowest=f"{slow:.2f}s")
 log(json.dumps(summary, ensure_ascii=False))
 return summary

def typo(query, seed):
 """The same search typed a little wrong: one swap, missing, extra or wrong letter in its longest word."""
 rng = random.Random(seed)
 longest = max(re.findall(r"\w+", query), key=len)
 if len(longest) < 5: return None
 i = rng.randrange(1, len(longest) - 1)
 w = rng.choice([lambda: longest[:i] + longest[i + 1] + longest[i] + longest[i + 2:],
                 lambda: longest[:i] + longest[i + 1:],
                 lambda: longest[:i] + rng.choice("aeiou") + longest[i:],
                 lambda: longest[:i] + rng.choice("aeiourstln".replace(longest[i], "")) + longest[i + 1:]])()
 return query.replace(longest, w, 1)

def with_typos(cases):
 out = []
 for n, c in enumerate(cases):
  q = c["want"] and typo(c["q"], n)
  if q and q != c["q"]: out.append(dict(c, q=q))
 return out

def load(path=None):
 """Hand-written cases plus every search you made in the palette and the file you opened from it."""
 cases = json.loads((path or config.STATE / "eval.json").read_text()) if (path or config.STATE / "eval.json").exists() else []
 try: lines = (config.STATE / "searches.jsonl").read_text().splitlines()
 except OSError: lines = []
 known = {c["q"] for c in cases}
 for line in lines[-300:]:
  try: s = json.loads(line)
  except ValueError: continue
  if s["q"] not in known and os.path.exists(s["path"]):
   known.add(s["q"]); cases.append(dict(q=s["q"], want=[os.path.basename(s["path"])], real=True))
 if not cases: raise FileNotFoundError(config.STATE / "eval.json")
 return cases
