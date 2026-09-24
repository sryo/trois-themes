# Checks every theme and builds the site: zips, previews, index.json and the gallery page.
import hashlib
import html
import io
import json
import os
import re
import shutil
import sys
import zipfile

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
THEMES = os.path.join(ROOT, "themes")
SITE = os.path.join(ROOT, "site")

# Kept in step with ThemeInstaller in Trois, which rejects anything else.
ALLOWED_EXTENSIONS = {"bmp", "png", "jpg", "jpeg", "gif", "tif", "tiff", "ico", "txt", "3dc", "ccs", "reg", "json"}
BUTTONS = ["close", "closeDown", "closeDisabled", "minimize", "minimizeDown", "minimizeDisabled",
           "zoom", "zoomDown", "zoomDisabled", "restore", "restoreDown", "help", "helpDown"]
MAX_FILE_BYTES = 1_000_000
MAX_ZIP_BYTES = 2_000_000
ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
# Zips are byte-identical across builds, so a theme's checksum only changes with its files.
ZIP_DATE = (1980, 1, 1, 0, 0, 0)


class ThemeError(Exception):
    pass


def check_theme(theme_id):
    path = os.path.join(THEMES, theme_id)
    if not ID_PATTERN.match(theme_id):
        raise ThemeError("folder name must be letters, digits, - or _")
    try:
        with open(os.path.join(path, "theme.json"), encoding="utf-8") as f:
            meta = json.load(f)
    except (OSError, ValueError) as e:
        raise ThemeError(f"theme.json: {e}")
    for key, kind in [("name", str), ("author", str), ("version", int), ("buttons", dict)]:
        if not isinstance(meta.get(key), kind):
            raise ThemeError(f"theme.json needs {key} ({kind.__name__})")
    for key in ("engine", "source"):
        if key in meta and not isinstance(meta[key], str):
            raise ThemeError(f"theme.json {key} must be a string")

    files = []
    for dirpath, dirnames, filenames in os.walk(path):
        for name in dirnames + filenames:
            full = os.path.join(dirpath, name)
            if os.path.islink(full):
                raise ThemeError(f"symlink not allowed: {name}")
        for name in filenames:
            rel = os.path.relpath(os.path.join(dirpath, name), path)
            if name == ".DS_Store":
                continue
            ext = name.rpartition(".")[2].lower()
            if ext not in ALLOWED_EXTENSIONS:
                raise ThemeError(f"file type not allowed: {rel}")
            if os.path.getsize(os.path.join(path, rel)) > MAX_FILE_BYTES:
                raise ThemeError(f"file over {MAX_FILE_BYTES} bytes: {rel}")
            files.append(rel)

    buttons = meta["buttons"]
    for key, rel in buttons.items():
        if key not in BUTTONS:
            raise ThemeError(f"unknown button {key}; use one of {', '.join(BUTTONS)}")
        if rel not in files:
            raise ThemeError(f"{key} points to missing file {rel}")
    if not any(k in buttons for k in ("close", "minimize", "zoom")):
        raise ThemeError("buttons needs at least one of close, minimize, zoom")
    return meta, sorted(files)


def build_zip(theme_id, files):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        for rel in files:
            info = zipfile.ZipInfo(f"{theme_id}/{rel}", ZIP_DATE)
            info.external_attr = 0o644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            with open(os.path.join(THEMES, theme_id, rel), "rb") as f:
                z.writestr(info, f.read())
    data = buffer.getvalue()
    if len(data) > MAX_ZIP_BYTES:
        raise ThemeError(f"zip over {MAX_ZIP_BYTES} bytes")
    return data


def build_previews(theme_id, buttons):
    previews = {}
    for key in ("close", "minimize", "zoom"):
        if key not in buttons:
            continue
        out = f"previews/{theme_id}/{key}.png"
        os.makedirs(os.path.dirname(os.path.join(SITE, out)), exist_ok=True)
        with Image.open(os.path.join(THEMES, theme_id, buttons[key])) as image:
            image.convert("RGBA").save(os.path.join(SITE, out))
        previews[key] = out
    return previews


def gallery(entries):
    cards = []
    for e in entries:
        images = "".join(
            f'<img src="{html.escape(e["preview"][k])}" alt="">' for k in ("close", "minimize", "zoom") if k in e["preview"]
        )
        cards.append(f"""      <li>
        <div class="preview">{images}</div>
        <h2>{html.escape(e["name"])}</h2>
        <p>by {html.escape(e["author"])}</p>
{f'        <p class="engine">{html.escape(e["engine"])}</p>{chr(10)}' if e.get("engine") else ""}        <a class="install" href="trois://install/{html.escape(e["id"])}">Install</a>
      </li>""")
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Trois Themes</title>
<style>
  :root {{ --bg: #f5f5f7; --card: #fff; --text: #1d1d1f; --muted: #6e6e73; --accent: #0071e3; --line: #d2d2d7; }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --bg: #1d1d1f; --card: #2c2c2e; --text: #f5f5f7; --muted: #a1a1a6; --accent: #2997ff; --line: #3a3a3c; }}
  }}
  body {{ margin: 0; background: var(--bg); color: var(--text); font: 15px/1.4 -apple-system, BlinkMacSystemFont, sans-serif; }}
  main {{ max-width: 960px; margin: 0 auto; padding: 32px 16px; }}
  h1 {{ font-weight: 300; font-size: 40px; margin: 0 0 8px; }}
  .intro {{ color: var(--muted); margin: 0 0 24px; }}
  ul {{ list-style: none; padding: 0; margin: 0; display: grid; grid-template-columns: repeat(auto-fill, minmax(170px, 1fr)); gap: 16px; }}
  li {{ background: var(--card); border: 1px solid var(--line); border-radius: 10px; padding: 16px; text-align: center; }}
  .preview {{ height: 48px; display: flex; align-items: center; justify-content: center; gap: 4px; }}
  .preview img {{ image-rendering: pixelated; }}
  h2 {{ font-size: 15px; font-weight: 600; margin: 8px 0 0; }}
  li p {{ color: var(--muted); font-size: 13px; margin: 2px 0 0; }}
  li p.engine {{ font-size: 12px; }}
  .install {{ display: inline-block; background: var(--accent); color: #fff; border-radius: 999px; padding: 4px 16px; margin-top: 12px; text-decoration: none; font-weight: 500; }}
  footer {{ color: var(--muted); font-size: 13px; margin-top: 32px; }}
  footer a {{ color: inherit; }}
</style>
</head>
<body>
<main>
  <h1>Trois Themes</h1>
  <p class="intro">Window themes from classic customizers like EppieDesktop and Kaleidoscope, ready to install in
    <a href="https://github.com/trois-dev/trois">Trois</a>. Install opens Trois and applies the theme.</p>
  <ul>
{chr(10).join(cards)}
  </ul>
  <footer>
    Each theme is the work of its author. See the
    <a href="https://github.com/trois-dev/trois#credits">credits</a> for the tools and archives they come from.
    If you made one of these and want it credited differently or removed,
    <a href="https://github.com/trois-dev/trois-themes/issues">open an issue</a>.
  </footer>
</main>
</body>
</html>
"""


def main():
    theme_ids = sorted(d for d in os.listdir(THEMES) if os.path.isdir(os.path.join(THEMES, d)))
    errors = []
    checked = []
    for theme_id in theme_ids:
        try:
            checked.append((theme_id, *check_theme(theme_id)))
        except ThemeError as e:
            errors.append(f"{theme_id}: {e}")
    if errors:
        print("\n".join(errors), file=sys.stderr)
        sys.exit(1)
    if "--check" in sys.argv:
        print(f"{len(checked)} themes ok")
        return

    shutil.rmtree(SITE, ignore_errors=True)
    os.makedirs(os.path.join(SITE, "themes"))
    entries = []
    for theme_id, meta, files in checked:
        data = build_zip(theme_id, files)
        download = f"themes/{theme_id}-{meta['version']}.zip"
        with open(os.path.join(SITE, download), "wb") as f:
            f.write(data)
        entries.append({
            "id": theme_id,
            "name": meta["name"],
            "author": meta["author"],
            "version": meta["version"],
            "size": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "download": download,
            "preview": build_previews(theme_id, meta["buttons"]),
            "engine": meta.get("engine"),
            "source": meta.get("source"),
        })

    with open(os.path.join(SITE, "index.json"), "w") as f:
        json.dump({"format": 1, "themes": entries}, f, indent=1)
        f.write("\n")
    with open(os.path.join(SITE, "index.html"), "w") as f:
        f.write(gallery(entries))
    print(f"built {len(entries)} themes into {os.path.relpath(SITE, ROOT)}")


if __name__ == "__main__":
    main()
