"""Turn files into searchable pieces: (location, text) chunks, image bytes and video frames."""
import html, io, json, re, shutil, subprocess, zipfile
from pathlib import Path

TEXT = {".txt", ".md", ".markdown", ".rst", ".org", ".tex", ".log", ".html", ".htm", ".xml", ".csv", ".tsv", ".srt", ".vtt"}
OFFICE = {".docx", ".odt", ".pptx", ".odp", ".xlsx", ".ods", ".epub", ".rtf"}
IMAGE = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff", ".avif"}
VIDEO = {".mp4", ".mkv", ".mov", ".webm", ".avi", ".m4v"}
AUDIO = {".mp3", ".ogg", ".oga", ".m4a", ".flac", ".wav", ".opus", ".aac"}
CODE = {".py", ".js", ".mjs", ".ts", ".tsx", ".jsx", ".go", ".rs", ".c", ".h", ".cc", ".cpp", ".hpp", ".java", ".kt",
        ".swift", ".rb", ".php", ".sh", ".bash", ".zsh", ".lua", ".sql", ".dart", ".ino", ".cs", ".scala", ".vue",
        ".svelte", ".css", ".scss", ".toml", ".yaml", ".yml", ".ipynb", ".json"}
SCREENSHOT = re.compile(r"screen|captura|print|whatsapp|shot|tela", re.I)

def kind(path):
 ext = path.suffix.lower()
 if ext == ".pdf": return "pdf"
 for name, exts in (("text", TEXT), ("office", OFFICE), ("image", IMAGE), ("video", VIDEO), ("audio", AUDIO), ("code", CODE)):
  if ext in exts: return name
 return "other"

def name_text(path):
 """Readable version of a file name, or '' when it is just a hash/number."""
 stem = re.sub(r"[_\-.+]+", " ", path.stem).strip()
 letters = sum(ch.isalpha() for ch in stem)
 if letters < 3 or re.fullmatch(r"[0-9a-f ]{8,}", stem.lower()): return ""
 return stem

def mostly_numeric(text):
 sample = text[:4000]
 return bool(sample) and sum(ch.isdigit() for ch in sample) / len(sample) > 0.35

def chunks(text, size=900, start_line=1):
 """Paragraph-aware chunks of about `size` chars, each tagged with its first line number."""
 out, buf, buf_line, line = [], [], start_line, start_line
 for para in re.split(r"(\n\s*\n)", text):
  if para.strip() and sum(map(len, buf)) + len(para) > size and buf:
   out.append((buf_line, "".join(buf).strip())); buf, buf_line = [], line
  while len(para) > size * 2:  # very long paragraph without blank lines
   out.append((line, para[:size].strip())); line += para[:size].count("\n"); para = para[size:]
  buf.append(para); line += para.count("\n")
 if "".join(buf).strip(): out.append((buf_line, "".join(buf).strip()))
 return [c for c in out if len(c[1]) > 2]

def run(*args, timeout=120, binary=False):
 r = subprocess.run(args, capture_output=True, timeout=timeout)
 return r.stdout if binary else r.stdout.decode(errors="replace")

def strip_tags(markup):
 markup = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", markup)
 markup = re.sub(r"(?i)<(br|/p|/div|/h\d|/li|/tr|/w:p|/text:p|/a:p)\b[^>]*>", "\n", markup)
 return html.unescape(re.sub(r"<[^>]+>", "", markup))

def read_text(path, limit=2_000_000):
 data = path.read_bytes()[:limit].decode(errors="replace")
 if path.suffix.lower() in (".html", ".htm", ".xml"): data = strip_tags(data)
 return data

def read_code(path):
 if path.suffix.lower() == ".ipynb":  # cells only, never outputs
  try: cells = json.loads(path.read_text(errors="replace")).get("cells", [])
  except ValueError: return []
  out, line = [], 1
  for cell in cells:
   src = "".join(cell.get("source", []))
   out += chunks(src, start_line=line); line += src.count("\n") + 1
  return out
 return chunks(read_text(path, 500_000), size=1200)

def read_office(path):
 ext = path.suffix.lower()
 if ext == ".rtf":
  raw = read_text(path)
  return chunks(re.sub(r"\\[a-z]+-?\d* ?|[{}]", "", raw))
 try: z = zipfile.ZipFile(path)
 except zipfile.BadZipFile: return []
 names = z.namelist()
 def xml(name): return z.read(name).decode(errors="replace")
 if ext == ".docx" and "word/document.xml" in names: return chunks(strip_tags(xml("word/document.xml")))
 if ext in (".odt", ".odp", ".ods") and "content.xml" in names: return chunks(strip_tags(xml("content.xml")))
 if ext == ".pptx":
  slides = sorted((n for n in names if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)), key=lambda n: int(re.findall(r"\d+", n)[0]))
  return [(i, t) for i, n in enumerate(slides, 1) for _, t in chunks(strip_tags(xml(n)))]
 if ext == ".xlsx" and "xl/sharedStrings.xml" in names: return chunks(strip_tags(xml("xl/sharedStrings.xml")))
 if ext == ".epub":
  pages = sorted(n for n in names if n.endswith((".xhtml", ".html", ".htm")))
  return [(i, t) for i, n in enumerate(pages, 1) for _, t in chunks(strip_tags(xml(n)))]
 return []

def pdf_pages(path):
 m = re.search(r"Pages:\s+(\d+)", run("pdfinfo", str(path), timeout=30))
 return int(m.group(1)) if m else 0

def ocr(image_path_or_bytes, langs):
 if not shutil.which("tesseract"): return ""
 if isinstance(image_path_or_bytes, bytes):
  r = subprocess.run(["tesseract", "-", "-", "-l", langs], input=image_path_or_bytes, capture_output=True, timeout=120)
  text = r.stdout.decode(errors="replace")
 else: text = run("tesseract", str(image_path_or_bytes), "-", "-l", langs)
 return re.sub(r"[ \t]+", " ", text).strip()

def read_pdf(path, first, last, langs=None, ocr_budget=6):
 """Chunks for pages first..last (1-based, inclusive). Scanned pages are OCRed within a budget."""
 text = run("pdftotext", "-f", str(first), "-l", str(last), str(path), "-", timeout=300)
 out = []
 for page, body in enumerate(text.split("\f"), first):
  if page > last: break
  if len(body.strip()) < 25 and langs and ocr_budget > 0:
   ocr_budget -= 1
   png = run("pdftoppm", "-f", str(page), "-l", str(page), "-r", "120", "-gray", "-png", str(path), timeout=120, binary=True)
   if png: body = ocr(png, langs)
  out += [(page, t) for _, t in chunks(body)]
 return out

def image_bytes(path, size=512):
 """Downscaled JPEG for the image encoder, or None if Pillow cannot read it."""
 try:
  from PIL import Image
  with Image.open(path) as im:
   im.seek(0); im = im.convert("RGB"); im.thumbnail((size, size))
   buf = io.BytesIO(); im.save(buf, "JPEG", quality=85); return buf.getvalue()
 except Exception: return None

def wants_ocr(path):
 return path.suffix.lower() in (".png", ".webp") or bool(SCREENSHOT.search(path.name))

def video_duration(path):
 try: return float(run("ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path), timeout=30).strip())
 except ValueError: return 0.0

def video_frames(path, max_frames):
 """Yield (second, jpeg_bytes): evenly spaced, at least four seconds apart."""
 duration = video_duration(path)
 if duration <= 0: return
 step = max(4.0, duration / max_frames)
 t = min(1.0, duration / 2)
 while t < duration:
  jpg = run("ffmpeg", "-v", "error", "-ss", f"{t:.2f}", "-i", str(path), "-frames:v", "1", "-vf", "scale=512:-2",
            "-f", "image2pipe", "-vcodec", "mjpeg", "-", timeout=60, binary=True)
  if jpg: yield int(t), jpg
  t += step

def ocr_langs():
 if not shutil.which("tesseract"): return None
 have = set(run("tesseract", "--list-langs").split())
 langs = [l for l in ("por", "eng", "spa") if l in have]
 return "+".join(langs) or None
