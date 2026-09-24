# Turns a theme submission issue into a folder under themes/, for the import workflow.
import json
import os
import re
import shutil
import stat
import sys
import tempfile
import urllib.request
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build  # noqa: E402

MAX_DOWNLOAD_BYTES = 5_000_000
MAX_UNZIPPED_BYTES = 10_000_000
MAX_ENTRIES = 200
# Only GitHub's own attachment links, so the workflow never fetches arbitrary URLs.
ATTACHMENT_PATTERN = re.compile(
    r"https://github\.com/(?:user-attachments/files|[\w.-]+/[\w.-]+/files)/\d+/[^\s)\]\"'<>]+\.zip",
    re.IGNORECASE,
)
ENGINES = {"EppieDesktop", "Kaleidoscope 1.x", "Kaleidoscope 2.x"}

# Mirrors the file name guessing in ThemeManager.swift. Down and disabled come first
# because some up patterns are substrings of them.
GUESSES = [
    ("closeDown", ["closedwn", "closedown", "close_down", "close down", "close button down", "close window button down", "close_dw", "1closedn"]),
    ("closeDisabled", ["closedis", "close_disable", "close disabled", "close button disabled", "close gray", "close_ds", "1closedis"]),
    ("close", ["closeup", "close_up", "close up", "close button up", "close window button", "1closeup"]),
    ("minimizeDown", ["mindwn", "mindown", "min_down", "min down", "min dwn", "mini_dwn", "minim_dw", "minimize_down", "minimize down", "minimize button down", "1mindn"]),
    ("minimizeDisabled", ["mindis", "min_disable", "min disabled", "min gray", "mini_dis", "minim_ds", "minimize_dis", "minimize button disabled", "1mindis"]),
    ("minimize", ["minup", "min_up", "min up", "mini_up", "minim_up", "minimize_up", "minimize up", "minimize button up", "1minup"]),
    ("zoomDown", ["maxdwn", "maxdown", "max_down", "max down", "max dwn", "maxim_dw", "maximize_down", "maximize down", "maximize button down", "1maxdn"]),
    ("zoomDisabled", ["maxdis", "max_disable", "max disabled", "max gray", "maxim_ds", "maximize_dis", "maximize button disabled", "1maxdis"]),
    ("zoom", ["maxup", "max_up", "max up", "maxim_up", "maximize_up", "maximize up", "maximize button up", "1maxup"]),
    ("restoreDown", ["resdwn", "resdown", "restore down", "restore_down", "restore_dw", "rst_dwn", "restore button down", "1resdn"]),
    ("restore", ["resup", "restore up", "restore_up", "restore button up", "rst_up", "1resup"]),
    ("helpDown", ["helpdwn", "helpdown", "help down", "help dwn", "help button down", "1helpdn"]),
    ("help", ["helpup", "help up", "help button up", "1helpup"]),
]
IMAGE_EXTENSIONS = {"bmp", "png", "jpg", "jpeg", "gif", "tif", "tiff"}


class SubmissionError(Exception):
    pass


def parse_form(body):
    # Issue forms render each field as "### Label" followed by the answer.
    fields = {}
    for section in re.split(r"^### ", body, flags=re.MULTILINE)[1:]:
        label, _, value = section.partition("\n")
        value = value.strip()
        fields[label.strip()] = "" if value == "_No response_" else value
    return fields


def download(url, dest):
    request = urllib.request.Request(url, headers={"User-Agent": "trois-themes-import"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response, open(dest, "wb") as f:
            total = 0
            while chunk := response.read(65536):
                total += len(chunk)
                if total > MAX_DOWNLOAD_BYTES:
                    raise SubmissionError(f"The zip is over {MAX_DOWNLOAD_BYTES // 1_000_000} MB.")
                f.write(chunk)
    except OSError as e:
        raise SubmissionError(f"Couldn't download the zip: {e}")


def safe_members(archive):
    members = []
    total = 0
    for info in archive.infolist():
        name = info.filename.replace("\\", "/")
        parts = [p for p in name.split("/") if p]
        if not parts or parts[0] == "__MACOSX" or parts[-1] == ".DS_Store" or parts[-1].startswith("._"):
            continue
        if name.startswith("/") or ".." in parts or ":" in parts[0]:
            raise SubmissionError(f"The zip has a path outside the theme folder: `{name}`")
        if stat.S_ISLNK(info.external_attr >> 16):
            raise SubmissionError(f"The zip has a symlink: `{name}`")
        if info.is_dir():
            continue
        total += info.file_size
        if total > MAX_UNZIPPED_BYTES or len(members) >= MAX_ENTRIES:
            raise SubmissionError("The zip is too large once unpacked.")
        members.append((info, parts))
    if not members:
        raise SubmissionError("The zip is empty.")
    # Drop a single top-level folder so both "theme/" and loose files work.
    while len({parts[0] for _, parts in members}) == 1 and all(len(parts) > 1 for _, parts in members):
        members = [(info, parts[1:]) for info, parts in members]
    return members


def guess_buttons(files):
    buttons = {}
    for rel in files:
        if "/" in rel or rel.rpartition(".")[2].lower() not in IMAGE_EXTENSIONS:
            continue
        stem = re.sub(r"\s+", " ", rel.rpartition(".")[0].lower())
        for key, patterns in GUESSES:
            if key not in buttons and any(p in stem for p in patterns):
                buttons[key] = rel
                break
    return buttons


def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:64]


def import_theme(fields, workdir):
    name = fields.get("Theme name", "").strip()
    author = fields.get("Author", "").strip()
    if not name or not author:
        raise SubmissionError("The theme name and author are required.")
    theme_id = slug(name)
    if not theme_id:
        raise SubmissionError("The theme name needs at least one letter or digit.")
    target = os.path.join(build.THEMES, theme_id)
    if os.path.exists(target):
        raise SubmissionError(f"A theme with the id `{theme_id}` already exists. Pick another name, or open a pull request to update it.")

    urls = ATTACHMENT_PATTERN.findall(fields.get("Theme zip", ""))
    if len(urls) != 1:
        raise SubmissionError("Attach exactly one .zip file in the Theme zip field.")
    zip_path = os.path.join(workdir, "theme.zip")
    download(urls[0], zip_path)
    try:
        archive = zipfile.ZipFile(zip_path)
    except zipfile.BadZipFile:
        raise SubmissionError("The attachment isn't a valid zip file.")

    with archive:
        members = safe_members(archive)
        os.makedirs(target)
        try:
            return _fill(target, theme_id, name, author, fields, archive, members)
        except BaseException:
            shutil.rmtree(target, ignore_errors=True)
            raise


def _fill(target, theme_id, name, author, fields, archive, members):
    for info, parts in members:
        dest = os.path.join(target, *parts)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with archive.open(info) as src, open(dest, "wb") as out:
            shutil.copyfileobj(src, out)

    manifest_path = os.path.join(target, "theme.json")
    meta = {}
    if os.path.exists(manifest_path):
        try:
            with open(manifest_path, encoding="utf-8") as f:
                meta = json.load(f)
        except ValueError as e:
            raise SubmissionError(f"theme.json in the zip isn't valid JSON: {e}")
        if not isinstance(meta, dict):
            raise SubmissionError("theme.json in the zip must be an object.")

    # The form is the source of truth for credits; the zip's theme.json supplies buttons.
    meta["name"] = name
    meta["author"] = author
    meta.setdefault("version", 1)
    engine = fields.get("Made for", "").strip()
    if engine in ENGINES:
        meta["engine"] = engine
    else:
        meta.pop("engine", None)
    source = fields.get("Source", "").strip()
    if source:
        meta["source"] = source
    if not meta.get("buttons"):
        files = sorted(
            os.path.relpath(os.path.join(d, f), target).replace(os.sep, "/")
            for d, _, fs in os.walk(target) for f in fs
        )
        meta["buttons"] = guess_buttons(files)
        if not meta["buttons"]:
            raise SubmissionError("Couldn't tell which image is which button. Add a theme.json to the zip, or name the images like `close_up.png` and `close_down.png`.")

    ordered = {k: meta[k] for k in ("name", "author", "version", "engine", "source", "buttons") if k in meta}
    ordered.update({k: v for k, v in meta.items() if k not in ordered})
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(ordered, f, indent=2, ensure_ascii=False)
        f.write("\n")

    try:
        build.check_theme(theme_id)
    except build.ThemeError as e:
        raise SubmissionError(f"The theme didn't pass the catalog check: {e}")
    return theme_id, name


def main():
    fields = parse_form(os.environ.get("ISSUE_BODY", ""))
    output = os.environ.get("GITHUB_OUTPUT")
    workdir = tempfile.mkdtemp()
    try:
        theme_id, name = import_theme(fields, workdir)
    except SubmissionError as e:
        with open(os.path.join(os.environ.get("RUNNER_TEMP", workdir), "import-error.md"), "w") as f:
            f.write(str(e) + "\n")
        print(e, file=sys.stderr)
        sys.exit(1)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    print(f"imported {theme_id}")
    if output:
        with open(output, "a") as f:
            f.write(f"id={theme_id}\n")
            f.write(f"name={' '.join(name.split())}\n")


if __name__ == "__main__":
    main()
