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

import frame

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


# Width in points of the close, minimize and zoom row a card draws, a dot
# standing in for a missing button. Same spacing as frame.draw_buttons.
def button_row(theme_id, buttons):
    widths = []
    for key in ("close", "minimize", "zoom"):
        image = frame.load_image(os.path.join(THEMES, theme_id, buttons[key])) if key in buttons else None
        widths.append(image.width if image else frame.DOT_SIZE)
    return sum(widths) + frame.BUTTON_GAP * (len(widths) - 1)


# The sidebar in a card's window: inset 4 on three sides, 40% of the window
# wide within 60 to 72, and wider when the buttons need it. Returns its width,
# or None when the window can't keep 72 beside it for the Install button.
# Kept in step with PreviewWindowLayout in the app.
SIDEBAR_INSET = 4
PLAIN_WINDOW = (144, 88)


def sidebar_width(window_width, row):
    width = max(min(72, max(60, round(window_width * 0.4))), row + 2 * SIDEBAR_INSET)
    return width if window_width - SIDEBAR_INSET - width >= 72 else None


def window_parts(window_width, row):
    """The sidebar for a card's window, and the hover button to put in the
    window beside it, or None when it goes over the whole card instead."""
    sb = sidebar_width(window_width, row)
    if not sb:
        return "", None
    sidebar = f'<div class="sidebar" style="width:{px(sb)}"></div>'
    return sidebar, action_button(SIDEBAR_INSET + sb)


# Centered right of `left`.
def action_button(left):
    return f'<span class="action" style="left:{px(left)}" aria-hidden="true"><span>Install</span></span>'



# Draws the frame for the gallery card, buttons included, so a card is one
# image. The app's Gallery tab reads it from index.json too.
def build_frame_preview(theme_id, name, buttons):
    paths = [os.path.join(THEMES, theme_id, buttons[k]) if k in buttons else None for k in ("close", "minimize", "zoom")]
    rendered = frame.preview(os.path.join(THEMES, theme_id, "frame"), name, paths)
    if rendered is None:
        return None
    out = f"previews/{theme_id}/frame.webp"
    os.makedirs(os.path.dirname(os.path.join(SITE, out)), exist_ok=True)
    rendered["image"].save(os.path.join(SITE, out), lossless=True, method=6)
    return {"image": out, "size": rendered["size"], "window": rendered["window"], "title": rendered["title"]}


# Orders by display name, skipping the leading punctuation old theme names use to sort first.
def sort_key(entry):
    name = entry["name"].casefold()
    return (re.sub(r"^[^0-9a-z]+", "", name) or name, entry["id"])


def px(value, unit="px"):
    return f"{value:g}{unit}"


def gallery(entries):
    engines = sorted({e["engine"] for e in entries if e.get("engine")})
    cards = []
    for e in entries:
        # A faint dot holds the spot of a button the theme doesn't have, like the app.
        buttons = "".join(
            f'<img src="{html.escape(e["preview"][k])}" alt="" loading="lazy">' if k in e["preview"] else '<span class="dot"></span>'
            for k in ("close", "minimize", "zoom")
        )
        framed = e.get("frame")
        window_width = framed["window"][2] if framed else PLAIN_WINDOW[0]
        sidebar, action = window_parts(window_width, e["buttonRow"])
        # Windows without a sidebar are too small to hold it, so it goes over the card.
        card_action = "" if action else action_button(0)
        action = action or ""
        if framed:
            fw, fh = framed["size"]
            wx, wy, ww, wh = framed["window"]
            title = ""
            if framed["title"]:
                tx, ty, tw, th = framed["title"]["box"]
                emboss = f';text-shadow:1px 1px 0 {framed["title"]["emboss"]}' if framed["title"].get("emboss") else ""
                title = (f'<span class="title" style="left:{px(tx)};top:{px(ty)};width:{px(tw)};height:{px(th)};'
                         f'line-height:{px(th)};color:{framed["title"]["color"]}{emboss}">{html.escape(e["name"])}</span>')
            # The frame image holds the buttons too.
            stage = (f'<div class="stage" style="--fw:{px(fw)};--fh:{px(fh)};--x:{px(wx)};--y:{px(wy)};--w:{px(ww)};--h:{px(wh)}">'
                     f'<div class="window">{sidebar}{action}</div><img class="frame" src="{html.escape(framed["image"])}" alt="" '
                     f'width="{px(fw, "")}" height="{px(fh, "")}" loading="lazy"><div class="corners">{sidebar}</div>{title}</div>')
        else:
            stage = f'<div class="stage"><div class="window plain">{sidebar}<div class="buttons">{buttons}</div>{action}</div></div>'
        engine = f'<p class="engine">{html.escape(e["engine"])}</p>' if e.get("engine") else ""
        source = e.get("source") or ""
        source_link = (
            f'<a class="source" href="{html.escape(source)}">Source</a>'
            if source.startswith(("https://", "http://")) else ""
        )
        search = html.escape(f'{e["name"]} {e["author"]}'.lower())
        cards.append(f'<li data-search="{search}" data-engine="{html.escape(e.get("engine") or "")}">'
                     f'<a class="card" href="trois://install/{html.escape(e["id"])}" title="Install and apply in Trois">'
                     f'<div class="desk">{stage}{card_action}</div>'
                     f'<h2>{html.escape(e["name"])}</h2><p>by {html.escape(e["author"])}</p>{engine}</a>{source_link}</li>')
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Trois Themes</title>
<style>
  :root {{ --bg: #f5f5f7; --desk: #e4e4e8; --window: #fff; --text: #1d1d1f; --muted: #6e6e73; --faint: #a1a1a6; --accent: #0071e3; --line: #d2d2d7; --sidebar: rgba(0, 0, 0, .06); }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --bg: #1d1d1f; --desk: #2c2c2e; --window: #3a3a3c; --text: #f5f5f7; --muted: #a1a1a6; --faint: #6e6e73; --accent: #2997ff; --line: #48484a; --sidebar: rgba(0, 0, 0, .2); }}
  }}
  body {{ margin: 0; background: var(--bg); color: var(--text); font: 15px/1.4 -apple-system, BlinkMacSystemFont, sans-serif; }}
  main {{ max-width: 960px; margin: 0 auto; padding: 32px 16px; }}
  h1 {{ font-weight: 300; font-size: 40px; margin: 0 0 8px; }}
  .intro {{ color: var(--muted); margin: 0 0 24px; }}
  .intro a, footer a {{ color: inherit; }}
  ul {{ list-style: none; padding: 0; margin: 0; display: grid; grid-template-columns: repeat(auto-fill, minmax(168px, 1fr)); gap: 24px 16px; }}
  li {{ text-align: center; min-width: 0; content-visibility: auto; contain-intrinsic-size: auto 200px; }}
  .controls {{ display: flex; flex-wrap: wrap; gap: 8px 12px; align-items: center; margin: 0 0 20px; }}
  .controls input {{ flex: 1 1 220px; font: inherit; color: inherit; background: var(--window); border: 1px solid var(--line); border-radius: 8px; padding: 7px 10px; }}
  .controls input:focus {{ outline: 2px solid var(--accent); outline-offset: -1px; }}
  .engines {{ display: flex; flex-wrap: wrap; gap: 6px; }}
  .engines button {{ font: inherit; font-size: 13px; color: var(--text); background: transparent; border: 1px solid var(--line); border-radius: 999px; padding: 4px 12px; cursor: pointer; }}
  .engines button[aria-pressed="true"] {{ background: var(--accent); border-color: var(--accent); color: #fff; }}
  .count {{ color: var(--muted); font-size: 13px; }}
  .empty {{ color: var(--muted); text-align: center; padding: 48px 0; }}
  .card {{ display: block; color: inherit; text-decoration: none; border-radius: 10px; outline: none; }}
  /* A small window on a desktop-like backdrop, like the app's theme grid. */
  .desk {{ position: relative; aspect-ratio: 3 / 2; background: var(--desk); border: 1px solid var(--line); border-radius: 8px; box-sizing: border-box; overflow: hidden;
    display: grid; place-items: center; transition: border-color .15s, box-shadow .15s; }}
  /* The app's 168x112 preview space, centered. Frames bigger than it are clipped. */
  .stage {{ position: relative; width: var(--fw, 168px); height: var(--fh, 112px); flex: none; }}
  .window {{ position: absolute; left: var(--x); top: var(--y); width: var(--w); height: var(--h); background: var(--window); border-radius: 8px; box-sizing: border-box; }}
  /* A sidebar down the window's left, so the buttons sit where most Mac apps put them. build.py sets its
     width to fit them. Kept in step with WindowSurface in the app. */
  .sidebar {{ position: absolute; left: 4px; top: 4px; bottom: 4px; border-radius: 4px; background: var(--sidebar); }}
  .window.plain {{ inset: 12px; border: 0.5px solid var(--line); box-shadow: 0 1px 3px rgba(0, 0, 0, .12); }}
  .frame {{ position: absolute; left: 0; top: 0; image-rendering: pixelated; }}
  /* The window's corners over the frame. On screen the window hides the corner fill that reaches under its
     edge; here the frame sits over the window, so the corners go back on top. Only the 8px corner squares
     show, clear of the buttons. Matches WindowCorners in the app. */
  .corners {{ position: absolute; left: var(--x); top: var(--y); width: var(--w); height: var(--h); background: var(--window); border-radius: 8px;
    --sq: linear-gradient(#000 0 0) no-repeat; mask: var(--sq) top left / 8px 8px, var(--sq) top right / 8px 8px, var(--sq) bottom left / 8px 8px, var(--sq) bottom right / 8px 8px; }}
  .buttons {{ position: absolute; inset: 0; padding: 8px; box-sizing: border-box; display: flex; align-items: flex-start; gap: 4px; }}
  .title {{ position: absolute; font-size: 12px; font-weight: 600; text-align: center; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
  /* Buttons draw at one CSS pixel per image pixel, like on screen. */
  .buttons img {{ image-rendering: pixelated; flex: none; }}
  .dot {{ width: 14px; height: 14px; border-radius: 50%; background: var(--faint); opacity: .4; flex: none; }}
  /* The card's action on hover, centered right of the sidebar or over the whole card when there's none, like the app. The whole card is the link. */
  .action {{ position: absolute; top: 0; right: 0; bottom: 0; display: grid; place-items: center; opacity: 0; transition: opacity .15s; pointer-events: none; }}
  .action span {{ background: var(--accent); color: #fff; font-size: 12px; font-weight: 600; padding: 5px 14px; border-radius: 999px; box-shadow: 0 1px 2px rgba(0, 0, 0, .2); }}
  /* 3px of accent: the 1px border and 2px around it. */
  .card:hover .desk, .card:focus-visible .desk {{ border-color: var(--accent); box-shadow: 0 0 0 2px var(--accent); }}
  .card:hover .action, .card:focus-visible .action {{ opacity: 1; }}
  h2 {{ font-size: 13px; font-weight: 500; margin: 8px 0 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
  li p {{ color: var(--muted); font-size: 12px; margin: 1px 0 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
  li p.engine {{ color: var(--faint); font-size: 11px; }}
  .source {{ display: inline-block; color: var(--accent); font-size: 12px; margin-top: 2px; text-decoration: none; }}
  .source:hover {{ text-decoration: underline; }}
  footer {{ color: var(--muted); font-size: 13px; margin-top: 40px; }}
</style>
</head>
<body>
<main>
  <h1>Trois Themes</h1>
  <p class="intro">{len(entries)} window themes from classic customizers like EppieDesktop and Kaleidoscope, ready for
    <a href="https://github.com/trois-dev/trois">Trois</a>. Click a theme to install and apply it in Trois.
    Made one? <a href="https://github.com/trois-dev/trois-themes/issues/new?template=submit_theme.yml">Submit a theme</a>.</p>
  <div class="controls">
    <input type="search" id="search" placeholder="Search by name or author" aria-label="Search themes" autocomplete="off">
    <div class="engines" role="group" aria-label="Engine">
{chr(10).join(f'      <button type="button" data-engine="{html.escape(x)}" aria-pressed="{str(x == "").lower()}">{html.escape(x or "All")}</button>' for x in ["", *engines])}
    </div>
    <span class="count" id="count" aria-live="polite"></span>
  </div>
  <ul id="themes">
{chr(10).join(cards)}
  </ul>
  <p class="empty" id="empty" hidden>No themes match.</p>
  <footer>
    Each theme is the work of its author. See the
    <a href="https://github.com/trois-dev/trois#credits">credits</a> for the tools and archives they come from.
    If you made one of these and want it credited differently or removed,
    <a href="https://github.com/trois-dev/trois-themes/issues">open an issue</a>.
  </footer>
</main>
<script>
  // Filters the cards by search text and engine. Without JavaScript every card shows.
  // Matches are put back into the list rather than hidden in place, which
  // restyles far less with thousands of cards.
  const list = document.getElementById("themes");
  const cards = [...list.children];
  const keys = cards.map(card => card.dataset.search);
  const cardEngines = cards.map(card => card.dataset.engine);
  const search = document.getElementById("search");
  const count = document.getElementById("count");
  const empty = document.getElementById("empty");
  const buttons = [...document.querySelectorAll(".engines button")];
  let engine = "";
  // Engine and words the list shows now. It starts with every card.
  let shownKey = "\\n";
  function update() {{
    const words = search.value.toLowerCase().split(/\\s+/).filter(Boolean);
    const key = engine + "\\n" + words.join(" ");
    if (key === shownKey) return;
    shownKey = key;
    const shown = cards.filter((card, i) => (!engine || cardEngines[i] === engine) && words.every(w => keys[i].includes(w)));
    list.replaceChildren(...shown);
    count.textContent = shown.length === cards.length ? `${{shown.length}} themes` : `${{shown.length}} of ${{cards.length}}`;
    empty.hidden = shown.length > 0;
  }}
  let timer;
  search.addEventListener("input", () => {{
    clearTimeout(timer);
    timer = setTimeout(update, 120);
  }});
  for (const button of buttons) {{
    button.addEventListener("click", () => {{
      engine = button.dataset.engine;
      buttons.forEach(b => b.setAttribute("aria-pressed", String(b === button)));
      clearTimeout(timer);
      update();
    }});
  }}
  // A search the browser restored still applies.
  count.textContent = `${{cards.length}} themes`;
  update();
</script>
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
            "buttonRow": button_row(theme_id, meta["buttons"]),
            "engine": meta.get("engine"),
            "source": meta.get("source"),
        })
        framed = build_frame_preview(theme_id, meta["name"], meta["buttons"])
        if framed:
            entries[-1]["frame"] = framed

    entries.sort(key=sort_key)
    with open(os.path.join(SITE, "index.json"), "w") as f:
        json.dump({"format": 1, "themes": entries}, f, indent=1)
        f.write("\n")
    with open(os.path.join(SITE, "index.html"), "w") as f:
        f.write(gallery(entries))
    print(f"built {len(entries)} themes into {os.path.relpath(SITE, ROOT)}")


if __name__ == "__main__":
    main()
