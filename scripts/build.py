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
# Kept in step with ButtonSlot in Trois, which saves these from its Editor tab.
BUTTONS = ["close", "closeHover", "closeDown", "closeDisabled",
           "minimize", "minimizeHover", "minimizeDown", "minimizeDisabled",
           "zoom", "zoomHover", "zoomDown", "zoomDisabled",
           "restore", "restoreDown", "help", "helpHover", "helpDown", "helpDisabled"]
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
# or None when the window can't keep 72 beside it.
# Kept in step with PreviewWindowLayout in the app.
SIDEBAR_INSET = 4
PLAIN_WINDOW = (144, 88)


def sidebar_width(window_width, row):
    width = max(min(72, max(60, round(window_width * 0.4))), row + 2 * SIDEBAR_INSET)
    return width if window_width - SIDEBAR_INSET - width >= 72 else None


def sidebar(window_width, row):
    sb = sidebar_width(window_width, row)
    return f'<div class="sidebar" style="width:{px(sb)}"></div>' if sb else ""


# Centered over the whole card, like the app.
ACTION = '<span class="action" aria-hidden="true"><span>Install</span></span>'



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


WEIGHTS = {"regular": 400, "medium": 500, "semibold": 600, "bold": 700, "heavy": 800}


# The frame's title style as inline CSS; the .title rule holds the defaults.
def title_css(t):
    css = [f'color:{t["color"]}']
    if t.get("shadow"):
        s = t["shadow"]
        css.append(f'text-shadow:{px(s["x"])} {px(s["y"])} {px(s["blur"])} {s["color"]}')
    elif t.get("emboss"):
        css.append(f'text-shadow:1px 1px 0 {t["emboss"]}')
    if t.get("font"):
        # Quotes stripped so a family name can't close the attribute.
        family = re.sub(r'["\'<>&;\\]', "", t["font"])
        css.append(f"font-family:'{family}',-apple-system,BlinkMacSystemFont,sans-serif")
    if t.get("size"):
        css.append(f'font-size:{px(t["size"])}')
    if t.get("weight"):
        css.append(f'font-weight:{WEIGHTS[t["weight"]]}')
    if t.get("align"):
        css.append(f'text-align:{t["align"]}')
    return ";".join(css)


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
        bar = sidebar(window_width, e["buttonRow"])
        if framed:
            fw, fh = framed["size"]
            wx, wy, ww, wh = framed["window"]
            title = ""
            if framed["title"]:
                tx, ty, tw, th = framed["title"]["box"]
                title = (f'<span class="title" style="left:{px(tx)};top:{px(ty)};width:{px(tw)};height:{px(th)};'
                         f'line-height:{px(th)};{title_css(framed["title"])}">{html.escape(e["name"])}</span>')
            # The frame image holds the buttons too.
            stage = (f'<div class="stage" style="--fw:{px(fw)};--fh:{px(fh)};--x:{px(wx)};--y:{px(wy)};--w:{px(ww)};--h:{px(wh)}">'
                     f'<div class="window">{bar}</div><img class="frame" src="{html.escape(framed["image"])}" alt="" '
                     f'width="{px(fw, "")}" height="{px(fh, "")}" loading="lazy"><div class="corners">{bar}</div>{title}</div>')
        else:
            stage = f'<div class="stage"><div class="window plain">{bar}<div class="buttons">{buttons}</div></div></div>'
        source = e.get("source") or ""
        source_link = (
            f'<a class="source" href="{html.escape(source)}">Source</a>'
            if source.startswith(("https://", "http://")) else ""
        )
        search = html.escape(f'{e["name"]} {e["author"]}'.lower())
        cards.append(f'<li data-search="{search}" data-engine="{html.escape(e.get("engine") or "")}">'
                     f'<a class="card" href="trois://install/{html.escape(e["id"])}" title="Install and apply in Trois">'
                     f'<div class="desk">{stage}{ACTION}</div>'
                     f'<h2>{html.escape(e["name"])}</h2><p>by {html.escape(e["author"])}</p></a>{source_link}</li>')
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Trois Themes</title>
<style>
  :root {{ --bg: #f5f5f7; --desk: #e4e4e8; --window: #fff; --text: #1d1d1f; --muted: #6e6e73; --faint: #a1a1a6; --accent: #0071e3; --line: #d2d2d7; --sidebar: rgba(0, 0, 0, .06); }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --bg: #1d1d1f; --desk: #323232; --window: #1e1e1e; --text: #f5f5f7; --muted: #a1a1a6; --faint: #6e6e73; --accent: #2997ff; --line: #48484a; --sidebar: rgba(255, 255, 255, .08); }}
  }}
  body {{ margin: 0; background: var(--bg); color: var(--text); font: 15px/1.4 -apple-system, BlinkMacSystemFont, sans-serif; }}
  main {{ max-width: 960px; margin: 0 auto; padding: 20px 16px 32px; }}
  footer a {{ color: inherit; }}
  ul {{ list-style: none; padding: 0; margin: 0; display: grid; grid-template-columns: repeat(auto-fill, minmax(168px, 1fr)); gap: 24px 16px; }}
  li {{ text-align: center; min-width: 0; content-visibility: auto; contain-intrinsic-size: auto 200px; }}
  /* One slim bar like a Mac toolbar, kept quiet so the thumbnails carry the color. */
  .bar {{ position: sticky; top: 0; z-index: 10; background: color-mix(in srgb, var(--bg) 88%, transparent);
    -webkit-backdrop-filter: saturate(1.4) blur(12px); backdrop-filter: saturate(1.4) blur(12px); border-bottom: 1px solid var(--line); }}
  .bar-in {{ max-width: 960px; margin: 0 auto; padding: 8px 16px; box-sizing: border-box; display: flex; align-items: center; gap: 10px; }}
  .bar h1 {{ font-size: 14px; font-weight: 600; margin: 0 6px 0 0; white-space: nowrap; }}
  .bar input, .bar select {{ font: inherit; font-size: 13px; color: var(--text); background: var(--window); border: 1px solid var(--line); border-radius: 6px; height: 28px; box-sizing: border-box; }}
  .bar input {{ flex: 1 1 auto; min-width: 0; max-width: 320px; padding: 0 8px; }}
  .bar select {{ padding: 0 6px; color: var(--muted); }}
  .bar input:focus, .bar select:focus {{ outline: 2px solid var(--accent); outline-offset: -1px; }}
  .count {{ font-size: 12px; color: var(--faint); white-space: nowrap; }}
  .links {{ margin-left: auto; display: flex; align-items: center; gap: 14px; font-size: 13px; white-space: nowrap; }}
  .submit {{ color: var(--muted); text-decoration: none; }}
  .submit:hover {{ color: var(--text); }}
  .get {{ position: relative; }}
  .get summary {{ list-style: none; cursor: pointer; color: var(--accent); padding: 4px 0; }}
  .get summary::-webkit-details-marker {{ display: none; }}
  .get summary:focus-visible, .submit:focus-visible {{ outline: 2px solid var(--accent); outline-offset: 2px; border-radius: 4px; }}
  .panel {{ position: absolute; right: 0; top: calc(100% + 8px); width: min(340px, calc(100vw - 32px)); box-sizing: border-box; white-space: normal;
    background: var(--window); border: 1px solid var(--line); border-radius: 10px; padding: 12px 14px; box-shadow: 0 8px 24px rgba(0, 0, 0, .12); }}
  .panel p {{ margin: 0; color: var(--muted); }}
  .panel ol {{ margin: 8px 0 0; padding-left: 18px; }}
  .panel li {{ text-align: left; content-visibility: visible; }}
  .panel li + li {{ margin-top: 3px; }}
  .panel a {{ color: var(--accent); }}
  /* Under 600px the bar takes two rows: title and links, then search and engine. */
  @media (max-width: 600px) {{
    .bar-in {{ flex-wrap: wrap; row-gap: 6px; }}
    .bar h1 {{ order: 1; }}
    .links {{ order: 2; }}
    .bar input {{ order: 3; flex: 1 1 50%; max-width: none; }}
    .bar select {{ order: 4; max-width: 44%; }}
    .count {{ display: none; }}
  }}
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
  /* The card's action on hover, centered over the whole card like the app. The whole card is the link. */
  .action {{ position: absolute; inset: 0; display: grid; place-items: center; opacity: 0; transition: opacity .15s; pointer-events: none; }}
  .action span {{ background: var(--accent); color: #fff; font-size: 12px; font-weight: 600; padding: 5px 14px; border-radius: 999px; box-shadow: 0 1px 2px rgba(0, 0, 0, .2); }}
  /* 3px of accent: the 1px border and 2px around it. */
  .card:hover .desk, .card:focus-visible .desk {{ border-color: var(--accent); box-shadow: 0 0 0 2px var(--accent); }}
  .card:hover .action, .card:focus-visible .action {{ opacity: 1; }}
  h2 {{ font-size: 13px; font-weight: 500; margin: 8px 0 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
  li p {{ color: var(--muted); font-size: 12px; margin: 1px 0 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
  .source {{ display: inline-block; color: var(--accent); font-size: 12px; margin-top: 2px; text-decoration: none; }}
  .source:hover {{ text-decoration: underline; }}
  footer {{ color: var(--muted); font-size: 13px; margin-top: 40px; }}
</style>
</head>
<body>
<header class="bar">
  <div class="bar-in">
    <h1>Trois Themes</h1>
    <input type="search" id="search" placeholder="Search {len(entries)} themes" aria-label="Search themes" autocomplete="off">
    <select id="engine" aria-label="Engine">
{chr(10).join(f'      <option value="{html.escape(x)}">{html.escape(x or "All engines")}</option>' for x in ["", *engines])}
    </select>
    <span class="count" id="count" aria-live="polite"></span>
    <div class="links">
      <a class="submit" href="https://github.com/trois-dev/trois-themes/issues/new?template=submit_theme.yml">Submit a theme</a>
      <details class="get">
        <summary>Get Trois</summary>
        <div class="panel">
          <p>Trois is a Mac app that applies these window themes.</p>
          <ol>
            <li>Download Trois from <a href="https://github.com/trois-dev/trois/releases">releases</a> (for Macs with Apple chips) and move it to Applications.</li>
            <li>Open it and allow Accessibility when asked.</li>
            <li>Click a theme. Trois downloads and applies it.</li>
          </ol>
        </div>
      </details>
    </div>
  </div>
</header>
<main>
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
  const engineSelect = document.getElementById("engine");
  // Engine and words the list shows now. It starts with every card.
  let shownKey = "\\n";
  function update() {{
    const words = search.value.toLowerCase().split(/\\s+/).filter(Boolean);
    const engine = engineSelect.value;
    const key = engine + "\\n" + words.join(" ");
    if (key === shownKey) return;
    shownKey = key;
    const shown = cards.filter((card, i) => (!engine || cardEngines[i] === engine) && words.every(w => keys[i].includes(w)));
    list.replaceChildren(...shown);
    // The search placeholder carries the total, so the count only shows while filtering.
    count.textContent = engine || words.length ? `${{shown.length}} of ${{cards.length}}` : "";
    empty.hidden = shown.length > 0;
  }}
  let timer;
  search.addEventListener("input", () => {{
    clearTimeout(timer);
    timer = setTimeout(update, 120);
  }});
  engineSelect.addEventListener("change", () => {{
    clearTimeout(timer);
    update();
  }});
  // Close the Get Trois panel on an outside click or Escape.
  const get = document.querySelector(".get");
  document.addEventListener("click", e => {{ if (!get.contains(e.target)) get.open = false; }});
  document.addEventListener("keydown", e => {{
    if (e.key === "Escape" && get.open) {{
      get.open = false;
      get.querySelector("summary").focus();
    }}
  }});
  // Without Trois a card's trois:// link does nothing, so if the page is still
  // in front a moment after a click, show how to get it.
  list.addEventListener("click", e => {{
    if (!e.target.closest("a.card")) return;
    let left = false;
    const away = () => {{ left = true; }};
    window.addEventListener("blur", away, {{ once: true }});
    document.addEventListener("visibilitychange", away, {{ once: true }});
    setTimeout(() => {{
      window.removeEventListener("blur", away);
      document.removeEventListener("visibilitychange", away);
      if (!left && document.hasFocus()) get.open = true;
    }}, 1500);
  }});
  // A search or engine the browser restored still applies.
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
