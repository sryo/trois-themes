# Draws a theme's window frame around a small window, like the theme grid in Trois.
#
# A port of FramePreview.swift, WindowFrame.swift and WindowFrameK1.swift, with
# the settings the grid starts with: an active window whose buttons sit at the
# traffic lights, not in the frame. The title isn't drawn; the page sets it as
# text in the returned title box. Coordinates are points with a top-left
# origin, and art draws at one point per image pixel.
import json
import math
import os

from PIL import Image, ImageDraw, ImageFont

CANVAS = (168, 112)
# Frames with very thick edges keep at least this much window and are clipped.
MIN_WINDOW = (64, 32)
SCALE = 2
CORNER_RADIUS = 8
# Points the corner fill reaches under the window's edge.
CORNER_OVERLAP = 2

# Part codes. See K2 Intro, chapter 3. CUT isn't in wnd#: a widget cut out of
# its section, never drawn, that still counts as part of the band.
EDGE, END_CAP, CLOSE, ZOOM, COLLAPSE = 0, 1, 2, 3, 4
TITLE, TITLE_CAP, STRETCH, CRUMPLE, STRETCH_END = 5, 6, 8, 10, 11
PERIOD, PERIOD_FILL, PERIOD_FILL_END = 12, 13, 14
NO_CLOSE, NO_ZOOM, NO_COLLAPSE, SCALED = 15, 16, 17, 18
CUT = -1
GROWS = {STRETCH, STRETCH_END, PERIOD, SCALED}
FILLS = {PERIOD_FILL, PERIOD_FILL_END}
# Widget rect code to its (with, without) part codes.
WIDGET_PARTS = {1: (CLOSE, NO_CLOSE), 2: (ZOOM, NO_ZOOM), 3: (COLLAPSE, NO_COLLAPSE)}

K1_INSETS = (22, 6, 6, 6)  # top, left, bottom, right
K1_STRIPE_TOP = 4
K1_WIDGET_GAP = 3
K1_TITLE_GAP = 6

_fonts = {}
TITLE_SIZE = 12
TITLE_SIZES = (8, 24)
TITLE_WEIGHTS = ("regular", "medium", "semibold", "bold", "heavy")
TITLE_ALIGNS = ("left", "center", "right")


# Stands in for the app's title font, 12 point semibold unless the frame's
# title style says otherwise, when sizing the title.
TITLE_WIDTH_BY_WEIGHT = {"regular": 0.96, "medium": 0.98, "bold": 1.03, "heavy": 1.06}


def title_width(text, style=None):
    size = title_size(style)
    if size not in _fonts:
        _fonts[size] = ImageFont.load_default(size)
    # Scaled up with room to spare, since browsers set it in their own font,
    # and by weight against the default semibold. Custom fonts aren't measured.
    weight = (style or {}).get("weight")
    factor = TITLE_WIDTH_BY_WEIGHT.get(weight, 1)
    return math.ceil(_fonts[size].getlength(text) * 1.12 * factor) + 2 + title_spill(style)


def title_size(style):
    size = (style or {}).get("size")
    if not isinstance(size, (int, float)) or isinstance(size, bool):
        return TITLE_SIZE
    # Fractional like the app's; the browser sets it as given.
    return min(max(size, TITLE_SIZES[0]), TITLE_SIZES[1])


def is_color(value):
    return isinstance(value, str) and len(value) in (7, 9) and value[0] == "#" and all(c in "0123456789abcdefABCDEF" for c in value[1:])


def custom_shadow(style):
    shadow = (style or {}).get("shadow")
    if not isinstance(shadow, dict) or not is_color(shadow.get("color")):
        return None
    def number(key, fallback):
        v = shadow.get(key, fallback)
        return v if isinstance(v, (int, float)) and not isinstance(v, bool) else fallback
    return {"color": shadow["color"], "x": number("x", 1), "y": number("y", 1), "blur": max(0, number("blur", 0))}


# Room for a custom shadow, like ResolvedTitle.spill.
def title_spill(style):
    shadow = custom_shadow(style)
    return abs(shadow["x"]) + shadow["blur"] if shadow else 0


def title_align(style):
    align = (style or {}).get("align")
    return align if align in TITLE_ALIGNS else "center"


def styled_title(box, style, color, emboss=None):
    """The title box for the page: `color` and `emboss` are what the art
    picks, and layout.json's title style overrides them, like TitleStyle.swift."""
    style = style or {}
    title = {"box": box, "color": style["color"] if is_color(style.get("color")) else color}
    shadow = custom_shadow(style)
    if shadow:
        title["shadow"] = shadow
    elif emboss and style.get("shadow") is not False:
        title["emboss"] = emboss
    font = style.get("font")
    if isinstance(font, str) and font and font != "system":
        title["font"] = font
    if title_size(style) != TITLE_SIZE:
        title["size"] = title_size(style)
    if style.get("weight") in TITLE_WEIGHTS and style["weight"] != "semibold":
        title["weight"] = style["weight"]
    if title_align(style) != "center":
        title["align"] = title_align(style)
    return title


class Segment:
    __slots__ = ("code", "start", "end", "out_start", "out_length")

    def __init__(self, code, start, end):
        self.code, self.start, self.end = code, start, end
        self.out_start = self.out_length = 0

    @property
    def length(self):
        return self.end - self.start


class Canvas:
    """An RGBA image at SCALE pixels per point that sources draw into."""

    def __init__(self, size):
        self.image = Image.new("RGBA", (round(size[0] * SCALE), round(size[1] * SCALE)), (0, 0, 0, 0))

    # Draws `source` (x0, y0, x1, y1 in image pixels) of `image` stretched into
    # `dest`, clipped to `clip`. Both in points.
    def draw(self, image, source, dest, clip=None):
        sx0, sy0, sx1, sy1 = (int(v) for v in source)
        dx0, dy0, dx1, dy1 = (round(v * SCALE) for v in dest)
        if sx1 <= sx0 or sy1 <= sy0 or dx1 <= dx0 or dy1 <= dy0:
            return
        piece = image.crop((sx0, sy0, sx1, sy1)).resize((dx1 - dx0, dy1 - dy0), Image.NEAREST)
        cx0, cy0, cx1, cy1 = (0, 0, *self.image.size)
        if clip:
            cx0, cy0 = max(cx0, round(clip[0] * SCALE)), max(cy0, round(clip[1] * SCALE))
            cx1, cy1 = min(cx1, round(clip[2] * SCALE)), min(cy1, round(clip[3] * SCALE))
        x0, y0, x1, y1 = max(dx0, cx0), max(dy0, cy0), min(dx1, cx1), min(dy1, cy1)
        if x1 <= x0 or y1 <= y0:
            return
        piece = piece.crop((x0 - dx0, y0 - dy0, x1 - dx0, y1 - dy0))
        self.image.alpha_composite(piece, (x0, y0))

    def clear(self, rect):
        box = tuple(round(v * SCALE) for v in rect)
        self.image.paste((0, 0, 0, 0), box)

    # Fills the gaps a window's rounded corners leave against the square
    # opening. The fill's curve sits inside the window's own, so the window's
    # antialiased edge blends over solid color.
    def fill_corners(self, hole, color):
        x0, y0, x1, y1 = hole
        r = min(CORNER_RADIUS, (x1 - x0) / 2, (y1 - y0) / 2)
        overlap = min(CORNER_OVERLAP, r)
        if r <= 0:
            return
        # Drawn 4x larger and scaled down for a smooth edge.
        k = SCALE * 4
        w, h = round((x1 - x0) * k), round((y1 - y0) * k)
        mask = Image.new("L", (w, h), 0)
        draw = ImageDraw.Draw(mask)
        rk = round(r * k)
        for cx, cy in ((0, 0), (w - rk, 0), (0, h - rk), (w - rk, h - rk)):
            draw.rectangle((cx, cy, cx + rk - 1, cy + rk - 1), fill=255)
        o = round(overlap * k)
        draw.rounded_rectangle((o, o, w - o - 1, h - o - 1), radius=round((r - overlap) * k), fill=0)
        mask = mask.resize((round((x1 - x0) * SCALE), round((y1 - y0) * SCALE)), Image.BOX)
        fill = Image.new("RGBA", mask.size, color + (255,))
        self.image.paste(fill, (round(x0 * SCALE), round(y0 * SCALE)), mask)


def pixel(image, x, y):
    """An opaque pixel's color, or None if it's transparent or outside."""
    if not (0 <= x < image.width and 0 <= y < image.height):
        return None
    r, g, b, a = image.getpixel((x, y))
    return (r, g, b) if a > 0 else None


def stored_color(image, x, y):
    """A pixel's color as stored, even where it's transparent, or None if outside."""
    if not (0 <= x < image.width and 0 <= y < image.height):
        return None
    return image.getpixel((x, y))[:3]


def hex_color(rgb):
    return "#%02x%02x%02x" % rgb


def load_image(path):
    try:
        with Image.open(path) as image:
            return image.convert("RGBA")
    except OSError:
        return None


class Frame:
    """A Kaleidoscope 2 document window: the art plus the wnd# layout that
    says how to stretch it."""

    def __init__(self, active, layout, title=None):
        self.active = active
        self.title_style = title
        self.size = active.size
        self.rects = {}
        for entry in layout.get("rects") or []:
            if len(entry) == 2 and isinstance(entry[0], int) and isinstance(entry[1], list) and len(entry[1]) == 4:
                # wnd# rects are (top, left, bottom, right) grid lines.
                t, l, b, r = entry[1]
                self.rects[entry[0]] = (l, t, r, b)
        c = self.rects.get(0)
        if not c or c[2] <= c[0] or c[3] <= c[1] or c[0] < 0 or c[1] < 0 or c[2] > self.size[0] or c[3] > self.size[1]:
            raise ValueError("bad content rect")
        self.content = c

        def side(key):
            return [(p[0], p[1]) for p in layout.get(key) or [] if len(p) == 2]
        self.top, self.bottom, self.left, self.right = side("top"), side("bottom"), side("left"), side("right")
        w, h = self.size
        self.insets = (c[1], c[0], h - c[3], w - c[2])

    def layout_edge(self, lst, extent, length, widgets, title_w, draws_end=lambda s, e: False):
        """Splits an edge list into drawn segments and places them along
        `length` points. Leading and trailing edge gaps keep their space;
        interior edge parts are dropped."""
        all_ = []
        position = 0
        for code, border in lst:
            # Some schemes run past the image; clamp like Kaleidoscope did.
            end = min(max(border, position), extent)
            all_.append(Segment(code, position, end))
            position = end
        drawn = [i for i, s in enumerate(all_) if s.code != EDGE and s.length > 0]
        if drawn:
            first, last = drawn[0], drawn[-1]
            for i, s in enumerate(all_):
                if s.code == EDGE and (i < first or i > last) and draws_end(s.start, s.end):
                    all_[i] = Segment(END_CAP, s.start, s.end)
        drawn = [s for s in all_ if s.code != EDGE and s.length > 0]
        lead = drawn[0].start if drawn else 0
        trail = max(0, extent - (drawn[-1].end if drawn else extent))

        def keep(s):
            if s.length <= 0 or s.code in (EDGE, CUT):
                return False
            for rect, (with_code, without_code) in WIDGET_PARTS.items():
                if s.code == with_code:
                    return rect in widgets
                if s.code == without_code:
                    return rect not in widgets
            if s.code in (TITLE, TITLE_CAP):
                return title_w is not None
            return True
        segments = [s for s in all_ if keep(s)]

        available = length - lead - trail
        title_rect = self.rects.get(4)

        # The title section grows so the text rect around it fits the text.
        def title_length(s):
            if title_w is None or title_rect is None:
                return s.length
            spill = (title_rect[2] - title_rect[0]) - s.length
            return max(s.length, title_w - spill)

        def fixed_length():
            return sum(title_length(s) if s.code == TITLE else s.length
                       for s in segments if s.code not in GROWS and s.code not in FILLS)
        # Crumple zones all go together when there isn't room for them.
        if fixed_length() > available:
            segments = [s for s in segments if s.code != CRUMPLE]
        spare = available - fixed_length()

        for s in segments:
            if s.code == TITLE:
                want = title_length(s)
                # Out of room: give back title space down to the drawn section.
                if spare < 0:
                    give = min(-spare, want - s.length)
                    want -= give
                    spare += give
                s.out_length = want
            elif s.code not in GROWS and s.code not in FILLS:
                s.out_length = s.length

        # Grow regions share what's left equally, the odd points going to the
        # last ones. Period repeats only take whole periods; fills and the
        # first stretch take the remainder.
        grows = [s for s in segments if s.code in GROWS]
        leftover = max(0, spare)
        if grows:
            share = leftover // len(grows)
            extra = leftover - share * len(grows)
            for n, s in enumerate(grows):
                give = share + (1 if n >= len(grows) - extra else 0)
                if s.code == PERIOD:
                    give = give // s.length * s.length
                s.out_length = give
            leftover -= sum(s.out_length for s in grows)
        if leftover > 0:
            fills = [s for s in segments if s.code in FILLS]
            if fills:
                share = leftover // len(fills)
                for s in fills:
                    s.out_length = share
                fills[0].out_length += leftover - share * len(fills)
            elif grows:
                target = next((s for s in grows if s.code != PERIOD), grows[0])
                target.out_length += leftover

        out = lead
        for s in segments:
            s.out_start = out
            out += s.out_length
        return segments

    def cut_out(self, hidden):
        """Hidden widgets whose sections stay with the button cut out, because
        the scheme has no art for a window without them."""
        codes = {code for code, _ in self.top + self.bottom + self.left + self.right}
        return {w for w in hidden if WIDGET_PARTS[w][0] in codes and WIDGET_PARTS[w][1] not in codes}

    def cutting(self, lst, cut, horizontal):
        """Splits each cut widget's section around the widget, grown by a
        point for its shadow."""
        out = []
        position = 0
        for code, border in lst:
            end = max(border, position)
            widget = next((w for w in cut if WIDGET_PARTS[w][0] == code), None)
            rect = self.rects.get(widget) if widget else None
            if rect:
                low = max(position, (rect[0] if horizontal else rect[1]) - 1)
                high = min(end, (rect[2] if horizontal else rect[3]) + 1)
                if low < high:
                    out += [(code, low), (CUT, high), (code, end)]
                    position = end
                    continue
            out.append((code, border))
            position = end
        return out

    def sides(self, outer, widgets, cut, title_w):
        width, height = outer
        iw, ih = self.size
        c = self.content

        def on(edge):
            return {w for w in cut if w in self.rects and edge(self.rects[w])}

        def mid(r):
            return (r[0] + r[2]) / 2, (r[1] + r[3]) / 2
        top_cut = on(lambda r: mid(r)[1] < c[1])
        bottom_cut = on(lambda r: mid(r)[1] > c[3])
        left_cut = on(lambda r: c[1] <= mid(r)[1] <= c[3] and mid(r)[0] < c[0])
        right_cut = on(lambda r: c[1] <= mid(r)[1] <= c[3] and mid(r)[0] > c[2])
        # End edge parts drawn by no other band: a side's end beside the
        # content, and the bottom band's corners.
        beside_content = lambda s, e: s >= c[1] and e <= c[3]
        bottom_corner = lambda s, e: e <= c[0] or s >= c[2]
        return (
            self.layout_edge(self.cutting(self.top, top_cut, True), iw, width, widgets | top_cut, title_w),
            self.layout_edge(self.cutting(self.bottom, bottom_cut, True), iw, width, widgets | bottom_cut, None, bottom_corner),
            self.layout_edge(self.cutting(self.left, left_cut, False), ih, height, widgets | left_cut, None, beside_content),
            self.layout_edge(self.cutting(self.right, right_cut, False), ih, height, widgets | right_cut, None, beside_content),
        )

    def fill(self, canvas, dest, source, code, horizontal):
        """Fills `dest` from `source` the way part `code` says: scaled, tiled
        from either end, or drawn once."""
        sw, sh = source[2] - source[0], source[3] - source[1]
        step = sw if horizontal else sh
        span = (dest[2] - dest[0]) if horizontal else (dest[3] - dest[1])
        if step <= 0:
            return
        if code == SCALED:
            canvas.draw(self.active, source, dest)
            return
        tiles = code in GROWS or code in FILLS or code == TITLE
        from_end = code in (STRETCH_END, PERIOD_FILL_END)
        for i in range(math.ceil(span / step) if tiles else 1):
            offset = span - step * (i + 1) if from_end else step * i
            x, y = (dest[0] + offset, dest[1]) if horizontal else (dest[0], dest[1] + offset)
            canvas.draw(self.active, source, (x, y, x + sw, y + sh), clip=dest)

    def render(self, window, title):
        top, left, bottom, right = self.insets
        outer = (window[0] + left + right, window[1] + top + bottom)
        c = self.content
        title_w = title_width(title, self.title_style) + 8
        # The grid draws every button at the traffic lights.
        hidden = set(WIDGET_PARTS)
        sides = self.sides(outer, set(), self.cut_out(hidden), title_w)
        canvas = Canvas(outer)

        # Sides first, over the full height, then top and bottom over them.
        for segments, sx, width, dx in ((sides[2], 0, c[0], 0), (sides[3], c[2], right, outer[0] - right)):
            for s in segments:
                if width > 0 and s.out_length > 0:
                    self.fill(canvas, (dx, s.out_start, dx + width, s.out_start + s.out_length),
                              (sx, s.start, sx + width, s.end), s.code, False)
        for segments, sy, height, dy in ((sides[0], 0, c[1], 0), (sides[1], c[3], bottom, outer[1] - bottom)):
            for s in segments:
                if height > 0 and s.out_length > 0:
                    self.fill(canvas, (s.out_start, dy, s.out_start + s.out_length, dy + height),
                              (s.start, sy, s.end, sy + height), s.code, True)

        hole = (left, top, left + window[0], top + window[1])
        canvas.clear(hole)
        edge = pixel(self.active, max(0, c[0] - 1), (c[1] + c[3]) // 2)
        if edge:
            canvas.fill_corners(hole, edge)

        title_box = None
        rect = self.rects.get(4)
        s = next((s for s in sides[0] if s.code == TITLE), None)
        if rect and s:
            before, after = s.start - rect[0], rect[2] - s.end
            x = s.out_start - before
            # Kaleidoscope's colors, like WindowFrame.resolvedTitle: text at the
            # content rect's top left, emboss right of it unless it matches.
            text = stored_color(self.active, c[0], c[1]) or (0, 0, 0)
            emboss = stored_color(self.active, c[0] + 1, c[1])
            title_box = styled_title((x, rect[1], s.out_length + before + after, rect[3] - rect[1]),
                                     self.title_style, hex_color(text),
                                     hex_color(emboss) if emboss and emboss != text else None)
        return canvas.image, outer, title_box


class K1Frame:
    """A Kaleidoscope 1.x scheme, drawn by fixed rules from its 16x16
    miniature window icon. See WindowFrameK1.swift for the rules."""

    def __init__(self, icon, stripes, pattern, title=None):
        self.icon, self.stripes, self.pattern = icon, stripes, pattern
        self.title_style = title
        self.insets = K1_INSETS

    def render(self, window, title):
        t, l, b, r = self.insets
        W, H = window[0] + l + r, window[1] + t + b
        canvas = Canvas((W, H))
        icon = self.icon

        # Columns: left border, stretched middle, right border.
        def band(sy, rows, dy, height):
            canvas.draw(icon, (0, sy, 6, sy + rows), (0, dy, 6, dy + height))
            canvas.draw(icon, (6, sy, 7, sy + rows), (6, dy, W - 6, dy + height))
            canvas.draw(icon, (10, sy, 16, sy + rows), (W - 6, dy, W, dy + height))
        # Title bar: top edge, stretched background, the lines above the content.
        band(0, 3, 0, 3)
        band(3, 1, 3, t - 5)
        band(4, 2, t - 2, 2)
        # Sides stretch row 7; the middle of the row is the ignored square.
        canvas.draw(icon, (0, 7, 6, 8), (0, t, 6, H - b))
        canvas.draw(icon, (10, 7, 16, 8), (W - 6, t, W, H - b))
        band(10, 6, H - 6, 6)

        hole = (l, t, l + window[0], t + window[1])
        canvas.clear(hole)
        edge = pixel(icon, 5, 7)
        if edge:
            canvas.fill_corners(hole, edge)

        # No widgets in the frame, so the stripes run the whole title bar.
        stripe_start = 4 + K1_WIDGET_GAP
        stripe_end = W - 4 - K1_WIDGET_GAP
        w = min(title_width(title, self.title_style), max(0, stripe_end - stripe_start - 2 * K1_TITLE_GAP))
        x = {"left": stripe_start + K1_TITLE_GAP, "right": stripe_end - K1_TITLE_GAP - w}.get(title_align(self.title_style), (W - w) / 2)
        box = (x, 3, w, t - 6)
        if self.stripes and stripe_end > stripe_start:
            y0, y1 = K1_STRIPE_TOP, K1_STRIPE_TOP + self.stripes.height
            # Stripes stop short of the title on both sides, each piece with its own ends.
            for x0, x1 in ((stripe_start, box[0] - K1_TITLE_GAP), (box[0] + w + K1_TITLE_GAP, stripe_end)):
                if x1 > x0:
                    self.draw_stripes(canvas, (x0, y0, x1, y1))

        # Kaleidoscope skips the emboss when it matches the text, not the background.
        text, emboss = pixel(icon, 7, 3), pixel(icon, 9, 3)
        title_box = styled_title(box, self.title_style, hex_color(text or (0, 0, 0)),
                                 hex_color(emboss) if emboss and emboss != text else None)
        return canvas.image, (W, H), title_box

    # Left half of the stripes icon at the start, right half at the end, the
    # middle column stretched between.
    def draw_stripes(self, canvas, rect):
        if self.pattern and self.pattern.width and self.pattern.height:
            # The pattern shows through the stripes' unmasked pixels.
            pw, ph = self.pattern.size
            y = rect[1]
            while y < rect[3]:
                x = rect[0]
                while x < rect[2]:
                    canvas.draw(self.pattern, (0, 0, pw, ph), (x, y, x + pw, y + ph), clip=rect)
                    x += pw
                y += ph
        s = self.stripes
        h, mid = s.height, s.width // 2
        right_w = s.width - mid - 1
        x0, y0, x1, _ = rect
        canvas.draw(s, (0, 0, mid, h), (x0, y0, x0 + mid, y0 + h), clip=rect)
        canvas.draw(s, (mid, 0, mid + 1, h), (x0 + mid, y0, max(x0 + mid, x1 - right_w), y0 + h), clip=rect)
        canvas.draw(s, (mid + 1, 0, s.width, h), (x1 - right_w, y0, x1, y0 + h), clip=rect)


def load(frame_dir):
    """The frame in a theme's frame folder, or None if it can't be read."""
    try:
        with open(os.path.join(frame_dir, "layout.json"), encoding="utf-8") as f:
            meta = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(meta, dict):
        return None
    active = load_image(os.path.join(frame_dir, "active.png"))
    if active is None:
        return None
    title = meta.get("title") if isinstance(meta.get("title"), dict) else None
    if meta.get("format") == "k1":
        if active.size != (16, 16):
            return None
        return K1Frame(active, load_image(os.path.join(frame_dir, "stripes.png")),
                       load_image(os.path.join(frame_dir, "stripes_pattern.png")), title)
    if not isinstance(meta.get("layout"), dict):
        return None
    try:
        return Frame(active, meta["layout"], title)
    except (ValueError, TypeError, IndexError):
        return None


# Buttons sit this far into the window, this far apart, like the page's CSS.
BUTTON_INSET = 8
BUTTON_GAP = 4
# A faint dot holds the spot of a missing button, like the page's .dot.
DOT_SIZE = 14
DOT_COLOR = (0xa1, 0xa1, 0xa6, round(255 * 0.4))


def draw_buttons(canvas, origin, buttons):
    """Draws the buttons left to right from `origin`, top aligned, at one
    point per image pixel. `buttons` holds an image path, or None for a dot."""
    x, y = origin
    for path in buttons:
        image = load_image(path) if path else None
        if image is None:
            k = SCALE * 4
            mask = Image.new("L", (DOT_SIZE * k, DOT_SIZE * k), 0)
            ImageDraw.Draw(mask).ellipse((0, 0, DOT_SIZE * k - 1, DOT_SIZE * k - 1), fill=DOT_COLOR[3])
            mask = mask.resize((DOT_SIZE * SCALE, DOT_SIZE * SCALE), Image.BOX)
            dot = Image.new("RGBA", mask.size, DOT_COLOR[:3] + (0,))
            dot.putalpha(mask)
            canvas.image.alpha_composite(dot, (round(x * SCALE), round(y * SCALE)))
            x += DOT_SIZE + BUTTON_GAP
            continue
        canvas.draw(image, (0, 0, *image.size), (x, y, x + image.width, y + image.height))
        x += image.width + BUTTON_GAP


def preview(frame_dir, title, buttons=()):
    """Renders the frame around a window that fills CANVAS, with `buttons`
    (see draw_buttons) at the window's top left. Returns the image at SCALE,
    its size in points, the window rect and the title box, or None."""
    frame = load(frame_dir)
    if frame is None:
        return None
    top, left, bottom, right = frame.insets
    window = (max(MIN_WINDOW[0], CANVAS[0] - left - right), max(MIN_WINDOW[1], CANVAS[1] - top - bottom))
    try:
        image, size, title_box = frame.render(window, title)
    except (ValueError, TypeError, IndexError, ZeroDivisionError):
        return None
    canvas = Canvas(size)
    canvas.image = image
    draw_buttons(canvas, (left + BUTTON_INSET, top + BUTTON_INSET), buttons)
    return {"image": image, "size": size, "window": (left, top, *window), "title": title_box}
