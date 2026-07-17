"""Token-based dual-theme system for Live Karaoke (Tkinter port of the web spec).

A single user-chosen ACCENT drives every highlight; everything else is neutral.
This is the desktop analog of the CSS custom-property system:

  * CSS `:root { --token: … }`  ->  a flat Python dict of tokens.
  * `html[data-theme=…]` override  ->  DARK / LIGHT base token dicts.
  * accent derivation in JS       ->  `derive_accent()` (colorsys).
  * localStorage persistence       ->  a small JSON prefs file.
  * an HSV colour-wheel picker      ->  `AccentPicker` (a Tk Canvas wheel).

Tkinter has no gradients/box-shadows, so `--headgrad`, `--bodyglow` and `--glow`
are approximated (flat header + a thin accent strip); every *colour* token is
honoured exactly.
"""
import base64
import colorsys
import json
import os
import tkinter as tk
from tkinter import ttk

import numpy as np

DEFAULT_ACCENT = "#025500"        # dimmed green
DEFAULT_MODE = "dark"
RADIUS = 12                        # --radius (used for conceptual spacing)

# --- neutral base tokens per theme (accent-derived tokens added at build time) --
DARK = {
    "bg": "#000000", "bg2": "#060606", "panel": "#101012", "panel2": "#17171a",
    "line": "#2a2a2e", "txt": "#ededed", "dim": "#9a9a9a",
    "warn": "#ffcc55", "err": "#ff5b5b",
}
LIGHT = {
    "bg": "#eef4ef", "bg2": "#e6ede8", "panel": "#ffffff", "panel2": "#f2f7f3",
    "line": "#cfe0d4", "txt": "#12251a", "dim": "#5c7a66",
    "warn": "#9a6b00", "err": "#b3261e",
}


# --------------------------------------------------------------- accent maths
def _hex_to_rgb(h):
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _rgb_to_hex(r, g, b):
    return "#%02x%02x%02x" % (int(round(r)), int(round(g)), int(round(b)))


def normalize_hex(h):
    """Return '#rrggbb' or None if invalid."""
    try:
        r, g, b = _hex_to_rgb(h)
    except Exception:
        return None
    return _rgb_to_hex(r, g, b)


def derive_accent(accent_hex):
    """Given the chosen accent, return {acc, acc2, acc_ink} exactly like the JS spec:
    acc2 = same hue, saturation >= 45%, lightness +20% (cap 75%);
    acc_ink = dark ink on light accents (YIQ > 140), else white."""
    acc = normalize_hex(accent_hex) or DEFAULT_ACCENT
    r, g, b = _hex_to_rgb(acc)
    h, l, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
    s2 = max(s, 0.45)
    l2 = min(l + 0.20, 0.75)
    r2, g2, b2 = colorsys.hls_to_rgb(h, l2, s2)
    acc2 = _rgb_to_hex(r2 * 255, g2 * 255, b2 * 255)
    yiq = (r * 299 + g * 587 + b * 114) / 1000
    acc_ink = "#08140a" if yiq > 140 else "#ffffff"
    return {"acc": acc, "acc2": acc2, "acc_ink": acc_ink}


def build_tokens(mode, accent_hex):
    base = dict(LIGHT if mode == "light" else DARK)
    base.update(derive_accent(accent_hex))
    base["mode"] = mode
    return base


# ------------------------------------------------------------------ prefs I/O
def _prefs_path():
    root = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(root, "LiveKaraoke", "prefs.json")


def load_prefs():
    try:
        with open(_prefs_path(), "r", encoding="utf-8") as f:
            d = json.load(f)
        mode = d.get("mode") if d.get("mode") in ("dark", "light") else DEFAULT_MODE
        accent = normalize_hex(d.get("accent", "")) or DEFAULT_ACCENT
        return {"mode": mode, "accent": accent}
    except Exception:
        return {"mode": DEFAULT_MODE, "accent": DEFAULT_ACCENT}


def save_prefs(mode, accent):
    try:
        p = _prefs_path()
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump({"mode": mode, "accent": accent}, f)
    except Exception:
        pass


class Theme:
    """Holds the current mode + accent and yields the live token dict."""

    def __init__(self, mode=DEFAULT_MODE, accent=DEFAULT_ACCENT):
        self.mode = mode if mode in ("dark", "light") else DEFAULT_MODE
        self.accent = normalize_hex(accent) or DEFAULT_ACCENT

    @property
    def tokens(self):
        return build_tokens(self.mode, self.accent)

    def toggle_mode(self):
        self.mode = "light" if self.mode == "dark" else "dark"

    def set_accent(self, hex_):
        self.accent = normalize_hex(hex_) or self.accent

    def save(self):
        save_prefs(self.mode, self.accent)


# ------------------------------------------------------- apply tokens -> ttk
def apply_styles(style, root, T):
    """Configure every ttk style + root chrome from the token dict. Re-callable
    live; widgets referencing these styles restyle automatically."""
    try:
        style.theme_use("clam")
    except Exception:
        pass
    acc, acc2, ink = T["acc"], T["acc2"], T["acc_ink"]
    bg, panel, panel2, line = T["bg"], T["panel"], T["panel2"], T["line"]
    txt, dim = T["txt"], T["dim"]

    root.configure(bg=bg)
    root.option_add("*TCombobox*Listbox.background", panel2)
    root.option_add("*TCombobox*Listbox.foreground", txt)
    root.option_add("*TCombobox*Listbox.selectBackground", acc)
    root.option_add("*TCombobox*Listbox.selectForeground", ink)

    style.configure(".", background=panel, foreground=txt, fieldbackground=panel2,
                    bordercolor=line, darkcolor=panel, lightcolor=panel,
                    troughcolor=panel2, focuscolor=acc2, insertcolor=txt, arrowcolor=txt)
    # neutral surfaces
    style.configure("TFrame", background=panel)
    style.configure("Bg.TFrame", background=bg)
    style.configure("TLabel", background=panel, foreground=txt)
    style.configure("Dim.TLabel", background=panel, foreground=dim)
    style.configure("Head.TLabel", background=panel, foreground=txt,
                    font=("Segoe UI Semibold", 13, "bold"))
    style.configure("TLabelframe", background=panel, bordercolor=line,
                    relief="solid", borderwidth=1)
    style.configure("TLabelframe.Label", background=panel, foreground=acc2,
                    font=("Segoe UI", 10, "bold"))
    # checkbutton
    style.configure("TCheckbutton", background=panel, foreground=txt, focuscolor=acc2)
    style.map("TCheckbutton",
              background=[("active", panel)],
              foreground=[("active", acc2)],
              indicatorcolor=[("selected", acc), ("!selected", panel2)])
    # neutral button (panel2 fill, border lifts to acc2 on hover)
    style.configure("TButton", background=panel2, foreground=txt, bordercolor=line,
                    focuscolor=panel, borderwidth=1, padding=(9, 4))
    style.map("TButton",
              background=[("active", panel2), ("pressed", panel2)],
              foreground=[("active", acc2), ("pressed", acc2)],
              bordercolor=[("active", acc2), ("focus", acc2)])
    # accent (primary) button
    style.configure("Accent.TButton", background=acc, foreground=ink, bordercolor=acc,
                    borderwidth=1, focuscolor=acc2, font=("Segoe UI", 11, "bold"),
                    padding=(12, 6))
    style.map("Accent.TButton",
              background=[("active", acc2), ("pressed", acc2)],
              foreground=[("active", ink), ("pressed", ink)],
              bordercolor=[("active", acc2)])
    # small icon button
    style.configure("Icon.TButton", background=panel2, foreground=txt, bordercolor=line,
                    borderwidth=1, padding=(7, 3), font=("Segoe UI", 11))
    style.map("Icon.TButton",
              background=[("active", panel2)],
              foreground=[("active", acc2)],
              bordercolor=[("active", acc2)])
    # scale
    style.configure("Horizontal.TScale", background=panel, troughcolor=panel2)
    # combobox
    style.configure("TCombobox", fieldbackground=panel2, background=panel2, foreground=txt,
                    arrowcolor=acc2, bordercolor=line, borderwidth=1, padding=(4, 2))
    style.map("TCombobox",
              fieldbackground=[("readonly", panel2)],
              foreground=[("readonly", txt)],
              selectbackground=[("readonly", panel2)],
              selectforeground=[("readonly", txt)],
              bordercolor=[("focus", acc2), ("active", acc2)],
              arrowcolor=[("active", acc)])
    # entry
    style.configure("TEntry", fieldbackground=panel2, foreground=txt, bordercolor=line,
                    insertcolor=txt, borderwidth=1, padding=(4, 3))
    style.map("TEntry", bordercolor=[("focus", acc2)])


# ------------------------------------------------------- HSV colour wheel img
def _wheel_photo(size, value, bg_hex):
    """Build an HSV wheel PhotoImage: hue = angle, saturation = radius, given
    Value. Pixels outside the disc take the surrounding bg colour."""
    n = int(size)
    axis = (np.arange(n) - (n - 1) / 2.0) / ((n - 1) / 2.0)  # -1..1
    dx = axis[None, :]
    dy = axis[:, None]
    r = np.sqrt(dx * dx + dy * dy)
    ang = np.arctan2(dy, dx)
    H = (ang / (2 * np.pi)) % 1.0
    S = np.clip(r, 0.0, 1.0)
    V = float(value)

    H6 = H * 6.0
    i = np.floor(H6).astype(int) % 6
    f = H6 - np.floor(H6)
    p = V * (1.0 - S)
    q = V * (1.0 - f * S)
    t = V * (1.0 - (1.0 - f) * S)
    Vf = np.full_like(S, V)
    cond = [i == 0, i == 1, i == 2, i == 3, i == 4, i == 5]
    R = np.select(cond, [Vf, q, p, p, t, Vf])
    G = np.select(cond, [t, Vf, Vf, q, p, p])
    B = np.select(cond, [p, p, t, Vf, Vf, q])
    rgb = np.stack([R, G, B], axis=-1)

    br, bgc, bb = _hex_to_rgb(bg_hex)
    outside = (r > 1.0)[..., None]
    bgarr = np.array([br, bgc, bb]) / 255.0
    rgb = np.where(outside, bgarr, rgb)
    arr = np.clip(rgb * 255.0, 0, 255).astype(np.uint8)

    header = ("P6\n%d %d\n255\n" % (n, n)).encode("ascii")
    b64 = base64.b64encode(header + arr.tobytes()).decode("ascii")
    try:
        return tk.PhotoImage(data=b64, format="ppm")
    except Exception:
        import tempfile
        fd, path = tempfile.mkstemp(suffix=".ppm")
        os.close(fd)
        with open(path, "wb") as fh:
            fh.write(header + arr.tobytes())
        img = tk.PhotoImage(file=path)
        try:
            os.remove(path)
        except Exception:
            pass
        return img


class AccentPicker(tk.Toplevel):
    """Modal HSV colour-wheel accent picker with a Brightness slider, hex input,
    live preview swatch and reset. Calls on_change(hex) live as the user drags."""

    def __init__(self, master, theme, on_change):
        super().__init__(master)
        self.theme = theme
        self.on_change = on_change
        self.title("Accent colour")
        self.resizable(False, False)
        self.transient(master)
        self._size = 210
        self._img = None
        self._pending = None

        T = theme.tokens
        self.configure(bg=T["panel"])
        r, g, b = _hex_to_rgb(theme.accent)
        h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        self._h, self._s, self._v = h, s, max(v, 0.06)

        wrap = ttk.Frame(self, padding=12)
        wrap.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(wrap, width=self._size, height=self._size,
                                highlightthickness=0, bd=0, bg=T["panel"], cursor="crosshair")
        self.canvas.pack()
        self.canvas.bind("<Button-1>", self._on_wheel)
        self.canvas.bind("<B1-Motion>", self._on_wheel)

        self.v_bright = tk.DoubleVar(value=self._v * 100)
        brow = ttk.Frame(wrap)
        brow.pack(fill="x", pady=(10, 4))
        ttk.Label(brow, text="Brightness").pack(side="left")
        self.sld = ttk.Scale(brow, from_=6, to=100, variable=self.v_bright,
                             command=self._on_bright)
        self.sld.pack(side="left", fill="x", expand=True, padx=8)

        hrow = ttk.Frame(wrap)
        hrow.pack(fill="x", pady=(6, 2))
        ttk.Label(hrow, text="Hex").pack(side="left")
        self.v_hex = tk.StringVar(value=theme.accent)
        self.ent = ttk.Entry(hrow, textvariable=self.v_hex, width=10)
        self.ent.pack(side="left", padx=6)
        self.ent.bind("<Return>", self._on_hex)
        self.ent.bind("<FocusOut>", self._on_hex)
        self.swatch = tk.Frame(hrow, width=26, height=26, bg=theme.accent,
                               highlightthickness=1, highlightbackground=T["line"])
        self.swatch.pack(side="left", padx=(6, 0))

        btns = ttk.Frame(wrap)
        btns.pack(fill="x", pady=(10, 0))
        ttk.Button(btns, text="Reset to default", command=self._reset).pack(side="left")
        ttk.Button(btns, text="Done", style="Accent.TButton",
                   command=self._done).pack(side="right")

        self._repaint()
        self.update_idletasks()
        try:  # centre on parent
            x = master.winfo_rootx() + (master.winfo_width() - self.winfo_width()) // 2
            y = master.winfo_rooty() + 60
            self.geometry(f"+{max(x,0)}+{max(y,0)}")
        except Exception:
            pass
        self.grab_set()

    # ---- rendering ----
    def _repaint(self):
        self._img = _wheel_photo(self._size, self._v, self.theme.tokens["panel"])
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor="nw", image=self._img)
        cx = cy = (self._size - 1) / 2.0
        rad = self._s * (self._size / 2.0)
        px = cx + rad * np.cos(self._h * 2 * np.pi)
        py = cy + rad * np.sin(self._h * 2 * np.pi)
        rr = 7
        ink = self.theme.tokens["acc2"]
        self.canvas.create_oval(px - rr, py - rr, px + rr, py + rr,
                                outline="#ffffff", width=2)
        self.canvas.create_oval(px - rr - 1, py - rr - 1, px + rr + 1, py + rr + 1,
                                outline=ink, width=1)

    def _emit(self):
        r, g, b = colorsys.hsv_to_rgb(self._h, self._s, self._v)
        hx = _rgb_to_hex(r * 255, g * 255, b * 255)
        self.v_hex.set(hx)
        try:
            self.swatch.config(bg=hx)
        except Exception:
            pass
        self.on_change(hx)

    # ---- interaction ----
    def _on_wheel(self, ev):
        cx = cy = (self._size - 1) / 2.0
        dx = (ev.x - cx) / (self._size / 2.0)
        dy = (ev.y - cy) / (self._size / 2.0)
        rr = min(1.0, (dx * dx + dy * dy) ** 0.5)
        self._h = (np.arctan2(dy, dx) / (2 * np.pi)) % 1.0
        self._s = rr
        self._draw_dot_only()
        self._emit()

    def _draw_dot_only(self):
        # cheap: repaint image only if needed; here just redraw dot over cached img
        self.canvas.delete("all")
        if self._img is not None:
            self.canvas.create_image(0, 0, anchor="nw", image=self._img)
        cx = cy = (self._size - 1) / 2.0
        rad = self._s * (self._size / 2.0)
        px = cx + rad * np.cos(self._h * 2 * np.pi)
        py = cy + rad * np.sin(self._h * 2 * np.pi)
        rr = 7
        self.canvas.create_oval(px - rr, py - rr, px + rr, py + rr, outline="#ffffff", width=2)
        self.canvas.create_oval(px - rr - 1, py - rr - 1, px + rr + 1, py + rr + 1,
                                outline=self.theme.tokens["acc2"], width=1)

    def _on_bright(self, _=None):
        self._v = max(0.06, float(self.v_bright.get()) / 100.0)
        if self._pending:
            self.after_cancel(self._pending)
        self._pending = self.after(40, self._repaint)
        self._emit()

    def _on_hex(self, _=None):
        hx = normalize_hex(self.v_hex.get())
        if not hx:
            return
        r, g, b = _hex_to_rgb(hx)
        h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        self._h, self._s, self._v = h, s, max(v, 0.06)
        self.v_bright.set(self._v * 100)
        self._repaint()
        self._emit()

    def _reset(self):
        self.v_hex.set(DEFAULT_ACCENT)
        self._on_hex()

    def _done(self):
        self.theme.save()
        self.grab_release()
        self.destroy()
