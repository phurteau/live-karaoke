"""Live Karaoke - turn your PC mic into a karaoke monitor.

Mic in -> effects (reverb, echo, chorus, auto-tune, pitch, cleanup) -> speakers,
in real time. USE HEADPHONES to avoid feedback howl.

Run:  python karaoke.py     (or double-click run_karaoke.bat)
"""
import os
import sys
import threading
import numpy as np
import sounddevice as sd
from pedalboard import (Pedalboard, HighpassFilter, NoiseGate, Compressor,
                        Chorus, Delay, Reverb, Gain, Limiter)

import dsp
import updater
import theme
from dsp import TDPitchShifter, detect_pitch, autotune_ratio, note_name, NOTE_NAMES

LATENCY_PRESETS = {
    "Ultra (128)": 128,
    "Low (256)": 256,
    "Balanced (512)": 512,
    "Safe (1024)": 1024,
}

DEFAULT_SETTINGS = dict(
    monitor_db=0.0, muted=False,
    lowcut=True, gate=False, gate_thresh=-55.0, comp=True,
    reverb=True, reverb_room=0.6, reverb_wet=0.28,
    echo=False, echo_time=0.28, echo_fb=0.30, echo_mix=0.25,
    chorus=False, chorus_mix=0.30,
    pitch_semi=0.0,
    autotune=False, at_key=0, at_scale='major', at_strength=0.90, at_retune=0.20,
)

PRESETS = {
    "Clean":        dict(reverb=False, echo=False, chorus=False, autotune=False, pitch_semi=0.0),
    "Karaoke":      dict(reverb=True, reverb_room=0.55, reverb_wet=0.25, echo=True,
                         echo_mix=0.18, echo_time=0.26, echo_fb=0.25, chorus=False,
                         autotune=False, comp=True, pitch_semi=0.0),
    "Concert Hall": dict(reverb=True, reverb_room=0.9, reverb_wet=0.45, echo=True,
                         echo_mix=0.22, echo_time=0.4, echo_fb=0.35, chorus=False, autotune=False),
    "T-Pain":       dict(autotune=True, at_scale='major', at_strength=1.0, at_retune=0.6,
                         reverb=True, reverb_wet=0.3, echo=True, echo_mix=0.2, comp=True),
    "Robot":        dict(autotune=True, at_scale='chromatic', at_strength=1.0, at_retune=0.9,
                         chorus=True, chorus_mix=0.5, reverb=False, echo=False),
    "Chipmunk":     dict(pitch_semi=5.0, autotune=False, reverb=True, reverb_wet=0.2),
    "Deep Voice":   dict(pitch_semi=-5.0, autotune=False, reverb=True, reverb_wet=0.25, comp=True),
}


# ------------------------------------------------------------------- engine
class KaraokeEngine:
    def __init__(self):
        self.sr = 48000
        self.out_ch = 2
        self.lock = threading.Lock()
        self.s = dict(DEFAULT_SETTINGS)
        self.running = False
        self.stream = None
        self.last_error = None
        self.xruns = 0
        self.mode = 'stopped'
        self.detected_note = '--'

        # persistent pedalboard plugins (order = signal chain after pitch shift)
        self.hp = HighpassFilter(cutoff_frequency_hz=90)
        self.gate = NoiseGate(threshold_db=-100, ratio=2.0, attack_ms=1, release_ms=100)
        self.comp = Compressor(threshold_db=-18, ratio=1.0, attack_ms=5, release_ms=120)
        self.chorus = Chorus(rate_hz=1.1, depth=0.25, centre_delay_ms=8, feedback=0.0, mix=0.0)
        self.delay = Delay(delay_seconds=0.28, feedback=0.3, mix=0.0)
        self.reverb = Reverb(room_size=0.6, damping=0.5, wet_level=0.0, dry_level=1.0, width=1.0)
        self.gain = Gain(gain_db=0.0)
        self.limiter = Limiter(threshold_db=-1.0, release_ms=100)
        self.board = Pedalboard([self.hp, self.gate, self.comp, self.chorus,
                                 self.delay, self.reverb, self.gain, self.limiter])

        self.ps = TDPitchShifter(grain=1536)
        self.analysis = np.zeros(2048, dtype=np.float32)
        self.cur_ratio = 1.0

    # ---- settings ----
    def update_settings(self, **kw):
        with self.lock:
            self.s.update(kw)

    def snapshot(self):
        with self.lock:
            return dict(self.s)

    # ---- processing ----
    def _apply_board(self, s):
        self.hp.cutoff_frequency_hz = 90.0 if s['lowcut'] else 15.0
        self.gate.threshold_db = float(s['gate_thresh']) if s['gate'] else -100.0
        self.comp.ratio = 3.0 if s['comp'] else 1.0
        self.chorus.mix = float(s['chorus_mix']) if s['chorus'] else 0.0
        self.delay.delay_seconds = float(np.clip(s['echo_time'], 0.02, 1.5))
        self.delay.feedback = float(np.clip(s['echo_fb'], 0.0, 0.95))
        self.delay.mix = float(s['echo_mix']) if s['echo'] else 0.0
        self.reverb.room_size = float(np.clip(s['reverb_room'], 0.0, 1.0))
        self.reverb.wet_level = float(np.clip(s['reverb_wet'], 0.0, 1.0)) if s['reverb'] else 0.0
        self.reverb.dry_level = 1.0
        self.gain.gain_db = float(np.clip(s['monitor_db'], -40.0, 18.0))

    def _process(self, mono, s):
        ratio = 2.0 ** (float(s['pitch_semi']) / 12.0)
        if s['autotune']:
            self.analysis = np.roll(self.analysis, -len(mono))
            self.analysis[-len(mono):] = mono
            f = detect_pitch(self.analysis, self.sr)
            self.detected_note = note_name(f)
            ratio *= autotune_ratio(f, int(s['at_key']), s['at_scale'], float(s['at_strength']))
            glide = float(s['at_retune'])
        else:
            self.detected_note = '--'
            glide = 0.5
        self.cur_ratio += (ratio - self.cur_ratio) * glide

        y = self.ps.process(mono, self.cur_ratio)
        self._apply_board(s)
        y = self.board(y, self.sr, reset=False)
        y = np.asarray(y).reshape(-1)
        if y.shape[0] != mono.shape[0]:
            out = np.zeros(mono.shape[0], dtype=np.float32)
            k = min(out.shape[0], y.shape[0])
            out[:k] = y[:k]
            y = out
        if s['muted']:
            y = np.zeros_like(y)
        return np.clip(y, -1.0, 1.0).astype(np.float32)

    def _callback(self, indata, outdata, frames, time_info, status):
        if status:
            self.xruns += 1
        try:
            mono = np.ascontiguousarray(indata[:, 0], dtype=np.float32)
            s = self.snapshot()
            y = self._process(mono, s)
            outdata[:] = y.reshape(-1, 1)
        except Exception as e:  # never raise out of the audio callback
            self.last_error = repr(e)
            outdata.fill(0)

    # ---- lifecycle ----
    def start(self, in_idx, out_idx, blocksize, exclusive=True):
        """Open a full-duplex stream. Prefers WASAPI *exclusive* mode (lowest
        latency, ~5-10 ms) and falls back to WASAPI shared, then the device's
        native host API, if exclusive isn't available."""
        if self.running:
            self.stop()
        din = sd.query_devices(in_idx)
        dout = sd.query_devices(out_idx)
        apis = sd.query_hostapis()
        in_api = apis[din['hostapi']]['name']
        out_api = apis[dout['hostapi']]['name']
        is_wasapi = ('WASAPI' in in_api) and ('WASAPI' in out_api)
        self.out_ch = max(1, min(2, int(dout['max_output_channels'])))

        self.ps.reset()
        self.cur_ratio = 1.0
        self.xruns = 0
        self.last_error = None

        def _open(sr, bs, extra, lat):
            st = sd.Stream(
                samplerate=sr, blocksize=bs, dtype='float32',
                device=(in_idx, out_idx), channels=(1, self.out_ch),
                latency=lat, callback=self._callback, extra_settings=extra,
            )
            try:
                st.start()
            except Exception:
                try:
                    st.close()
                except Exception:
                    pass
                raise
            return st

        attempts = []
        if is_wasapi and exclusive:
            # Exclusive mode: request an explicit, tiny buffer. WASAPI clamps up
            # to the driver's minimum period, so we ladder from small to larger.
            sr = int(round(din['default_samplerate']))
            try:
                ex = (sd.WasapiSettings(exclusive=True), sd.WasapiSettings(exclusive=True))
                for frames in sorted({blocksize, 128, 240, 480, 1024}):
                    lat = frames / float(sr)
                    attempts.append((f'WASAPI exclusive {frames}', sr, frames, ex, lat))
            except Exception:
                pass
        if is_wasapi:
            try:
                sh = (sd.WasapiSettings(auto_convert=True), sd.WasapiSettings(auto_convert=True))
            except Exception:
                sh = None
            attempts.append(('WASAPI shared', 48000, blocksize, sh, blocksize / 48000.0))
        # Last resort: native host API (MME/DirectSound) at the device rate.
        native_sr = int(round(min(din['default_samplerate'], dout['default_samplerate'])))
        attempts.append((in_api if not is_wasapi else 'WASAPI shared (fallback)',
                         native_sr, blocksize, None, 'low'))

        errors = []
        for name, sr, bs, extra, lat in attempts:
            try:
                self.stream = _open(sr, bs, extra, lat)
                self.sr = sr
                self.mode = name
                self.running = True
                if errors:
                    self.last_error = None
                return
            except Exception as e:
                errors.append(f"{name}: {e}")
        self.mode = 'stopped'
        raise RuntimeError("Could not open an audio stream.\n" + "\n".join(errors))

    def stop(self):
        self.running = False
        self.mode = 'stopped'
        if self.stream is not None:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
            self.stream = None

    def status(self):
        cpu = 0.0
        lat = 0.0
        if self.stream is not None:
            try:
                cpu = self.stream.cpu_load
                lat = self.stream.latency[0] + self.stream.latency[1]
            except Exception:
                pass
        return dict(running=self.running, cpu=cpu, latency=lat,
                    xruns=self.xruns, note=self.detected_note,
                    error=self.last_error, sr=self.sr, mode=self.mode)


# --------------------------------------------------------------- device utils
def list_devices():
    devs = sd.query_devices()
    apis = sd.query_hostapis()
    ins, outs = [], []
    for i, d in enumerate(devs):
        api = apis[d['hostapi']]['name']
        label = f"[{api}] {d['name']}"
        if d['max_input_channels'] > 0:
            ins.append((i, label))
        if d['max_output_channels'] > 0:
            outs.append((i, label))
    return ins, outs


def default_devices():
    try:
        d = sd.default.device
        return d[0], d[1]
    except Exception:
        return None, None


def wasapi_defaults():
    """Return (input_idx, output_idx) for the WASAPI host API's default
    devices - i.e. your real default mic/speakers on the low-latency path."""
    try:
        for a in sd.query_hostapis():
            if 'WASAPI' in a['name']:
                di = a.get('default_input_device', -1)
                do = a.get('default_output_device', -1)
                return (di if di is not None and di >= 0 else None,
                        do if do is not None and do >= 0 else None)
    except Exception:
        pass
    return None, None


def preferred_defaults():
    """Prefer WASAPI default devices; fall back to the system defaults."""
    wi, wo = wasapi_defaults()
    di, do = default_devices()
    return (wi if wi is not None else di), (wo if wo is not None else do)


# ------------------------------------------------------------------- the GUI
def run_gui():
    import tkinter as tk
    from tkinter import ttk, messagebox

    engine = KaraokeEngine()
    root = tk.Tk()
    root.title(f"Live Karaoke  v{updater.__version__}")
    root.geometry("620x860")
    root.minsize(580, 780)

    style = ttk.Style(root)
    try:
        style.theme_use('clam')
    except Exception:
        pass
    # ---- token-based theme (dark default; one accent drives all highlights) ----
    _prefs = theme.load_prefs()
    thm = theme.Theme(_prefs["mode"], _prefs["accent"])
    T = dict(thm.tokens)               # live token holder, refreshed by restyle()
    theme.apply_styles(style, root, T)

    ins, outs = list_devices()
    din, dout = preferred_defaults()
    in_labels = [l for _, l in ins]
    out_labels = [l for _, l in outs]
    in_idx_map = [i for i, _ in ins]
    out_idx_map = [i for i, _ in outs]

    # ---- tk variables ----
    v_in = tk.StringVar(value=(next((l for i, l in ins if i == din), in_labels[0] if in_labels else "")))
    v_out = tk.StringVar(value=(next((l for i, l in outs if i == dout), out_labels[0] if out_labels else "")))
    v_lat = tk.StringVar(value="Ultra (128)")
    v_excl = tk.BooleanVar(value=False)

    v = dict(
        monitor_db=tk.DoubleVar(value=0.0),
        muted=tk.BooleanVar(value=False),
        lowcut=tk.BooleanVar(value=True),
        gate=tk.BooleanVar(value=False),
        gate_thresh=tk.DoubleVar(value=-55.0),
        comp=tk.BooleanVar(value=True),
        reverb=tk.BooleanVar(value=True),
        reverb_room=tk.DoubleVar(value=0.6),
        reverb_wet=tk.DoubleVar(value=0.28),
        echo=tk.BooleanVar(value=False),
        echo_time=tk.DoubleVar(value=0.28),
        echo_fb=tk.DoubleVar(value=0.30),
        echo_mix=tk.DoubleVar(value=0.25),
        chorus=tk.BooleanVar(value=False),
        chorus_mix=tk.DoubleVar(value=0.30),
        pitch_semi=tk.DoubleVar(value=0.0),
        autotune=tk.BooleanVar(value=False),
        at_key=tk.StringVar(value='C'),
        at_scale=tk.StringVar(value='major'),
        at_strength=tk.DoubleVar(value=0.90),
        at_retune=tk.DoubleVar(value=0.20),
    )

    def sync(*_):
        engine.update_settings(
            monitor_db=v['monitor_db'].get(), muted=v['muted'].get(),
            lowcut=v['lowcut'].get(), gate=v['gate'].get(),
            gate_thresh=v['gate_thresh'].get(), comp=v['comp'].get(),
            reverb=v['reverb'].get(), reverb_room=v['reverb_room'].get(),
            reverb_wet=v['reverb_wet'].get(),
            echo=v['echo'].get(), echo_time=v['echo_time'].get(),
            echo_fb=v['echo_fb'].get(), echo_mix=v['echo_mix'].get(),
            chorus=v['chorus'].get(), chorus_mix=v['chorus_mix'].get(),
            pitch_semi=v['pitch_semi'].get(),
            autotune=v['autotune'].get(),
            at_key=NOTE_NAMES.index(v['at_key'].get()),
            at_scale=v['at_scale'].get(),
            at_strength=v['at_strength'].get(),
            at_retune=v['at_retune'].get(),
        )

    for var in v.values():
        var.trace_add('write', sync)

    # ---- layout ----
    pad = dict(padx=8, pady=3)

    # ---- header bar: title + theme toggle + accent picker ----
    bar = ttk.Frame(root)
    bar.pack(fill='x')
    title_lbl = ttk.Label(bar, text="🎤  Live Karaoke", style='Head.TLabel')
    title_lbl.pack(side='left', padx=12, pady=7)
    btn_theme = ttk.Button(bar, text="☀", style='Icon.TButton', width=3)
    btn_accent = ttk.Button(bar, text="🎨  Color", style='Icon.TButton')
    btn_theme.pack(side='right', padx=(0, 12), pady=6)
    btn_accent.pack(side='right', padx=(0, 6), pady=6)

    banner = tk.Label(root, text="🎧  USE HEADPHONES  -  speakers will cause feedback howl",
                      font=('Segoe UI', 9, 'bold'))
    banner.pack(fill='x')

    # ---- update banner (hidden until a newer release is detected) ----
    upd_bar = tk.Frame(root)
    upd_state = {"info": None, "busy": False}
    upd_lbl = tk.Label(upd_bar, font=('Segoe UI', 9, 'bold'), anchor='w')
    upd_lbl.pack(side='left', padx=10, pady=4)

    def _upd_open_notes():
        info = upd_state["info"]
        if info:
            import webbrowser
            webbrowser.open(info["url"])

    def _upd_restart():
        if updater.relaunch():
            engine.stop()
            root.destroy()
        else:
            messagebox.showinfo("Restart", "Update applied. Please close and reopen the app.")

    def _upd_do_update():
        info = upd_state["info"]
        if not info or upd_state["busy"]:
            return
        upd_state["busy"] = True
        upd_btn.config(state='disabled', text="Updating…")
        upd_notes_btn.config(state='disabled')

        def worker():
            ok, msg = updater.apply_update(info)
            if ok:
                updater.sync_dependencies()

            def done():
                upd_state["busy"] = False
                upd_notes_btn.config(state='normal')
                if ok:
                    upd_lbl.config(text=f"✅  Updated to v{info['version']} - restart to apply.")
                    upd_btn.config(state='normal', text="⟳  Restart now", command=_upd_restart)
                else:
                    upd_btn.config(state='normal', text="Retry update", command=_upd_do_update)
                    messagebox.showerror("Update failed", msg)
            root.after(0, done)
        threading.Thread(target=worker, daemon=True).start()

    upd_notes_btn = ttk.Button(upd_bar, text="Release notes", command=_upd_open_notes)
    upd_btn = ttk.Button(upd_bar, text="⬇  Update now", style='Accent.TButton', command=_upd_do_update)
    upd_dismiss = ttk.Button(upd_bar, text="✕", width=3, command=lambda: upd_bar.pack_forget())
    upd_dismiss.pack(side='right', padx=(0, 6), pady=3)
    upd_notes_btn.pack(side='right', padx=(0, 6), pady=3)
    upd_btn.pack(side='right', padx=(0, 6), pady=3)

    def _show_update(info):
        try:
            upd_state["info"] = info
            upd_lbl.config(text=f"🔔  New version v{info['version']} available "
                                f"(you have v{updater.__version__})")
            upd_bar.pack(fill='x', after=banner)
        except Exception:
            pass

    def _check_updates():
        try:
            cur = os.environ.get('KARAOKE_FAKE_VERSION', updater.__version__)
            info = updater.check_for_update(cur)
            if info:
                root.after(0, lambda: _show_update(info))
        except Exception:
            pass
    threading.Thread(target=_check_updates, daemon=True).start()

    top = ttk.Frame(root); top.pack(fill='x', **pad)
    ttk.Label(top, text="Mic in").grid(row=0, column=0, sticky='w')
    cb_in = ttk.Combobox(top, textvariable=v_in, values=in_labels, state='readonly', width=52)
    cb_in.grid(row=0, column=1, columnspan=3, sticky='we', pady=2)
    ttk.Label(top, text="Output").grid(row=1, column=0, sticky='w')
    cb_out = ttk.Combobox(top, textvariable=v_out, values=out_labels, state='readonly', width=52)
    cb_out.grid(row=1, column=1, columnspan=3, sticky='we', pady=2)
    ttk.Label(top, text="Latency").grid(row=2, column=0, sticky='w')
    cb_lat = ttk.Combobox(top, textvariable=v_lat, values=list(LATENCY_PRESETS), state='readonly', width=16)
    cb_lat.grid(row=2, column=1, sticky='w', pady=2)
    chk_excl = ttk.Checkbutton(top, text="Exclusive mode (lowest latency)", variable=v_excl)
    chk_excl.grid(row=2, column=2, columnspan=2, sticky='w', padx=(10, 0))
    top.columnconfigure(1, weight=1)

    ctrl = ttk.Frame(root); ctrl.pack(fill='x', **pad)
    btn_start = ttk.Button(ctrl, text="▶  START", style='Accent.TButton')
    btn_start.pack(side='left', ipady=6, ipadx=10)
    ttk.Checkbutton(ctrl, text="Mute", variable=v['muted']).pack(side='left', padx=12)
    ttk.Label(ctrl, text="Monitor vol").pack(side='left', padx=(12, 4))
    ttk.Scale(ctrl, from_=-40, to=18, variable=v['monitor_db'], length=150).pack(side='left')

    # presets
    pf = ttk.Frame(root); pf.pack(fill='x', **pad)
    ttk.Label(pf, text="Presets:").pack(side='left')

    def slider(parent, label, var, lo, hi, fmt="{:.2f}"):
        row = ttk.Frame(parent); row.pack(fill='x', pady=1)
        ttk.Label(row, text=label, width=12).pack(side='left')
        val = ttk.Label(row, width=7, text=fmt.format(var.get()))
        val.pack(side='right')
        s = ttk.Scale(row, from_=lo, to=hi, variable=var, length=230)
        s.pack(side='left', fill='x', expand=True, padx=6)
        var.trace_add('write', lambda *_: val.config(text=fmt.format(var.get())))
        return row

    # Voice cleanup
    f1 = ttk.Labelframe(root, text="Voice cleanup"); f1.pack(fill='x', **pad)
    r = ttk.Frame(f1); r.pack(fill='x')
    ttk.Checkbutton(r, text="Low-cut", variable=v['lowcut']).pack(side='left', padx=6)
    ttk.Checkbutton(r, text="Compressor", variable=v['comp']).pack(side='left', padx=6)
    ttk.Checkbutton(r, text="Noise gate", variable=v['gate']).pack(side='left', padx=6)
    slider(f1, "Gate thresh", v['gate_thresh'], -80, -20, "{:.0f} dB")

    # Reverb
    f2 = ttk.Labelframe(root, text="Reverb"); f2.pack(fill='x', **pad)
    ttk.Checkbutton(f2, text="Enable", variable=v['reverb']).pack(anchor='w', padx=6)
    slider(f2, "Room size", v['reverb_room'], 0.0, 1.0)
    slider(f2, "Amount", v['reverb_wet'], 0.0, 1.0)

    # Echo
    f3 = ttk.Labelframe(root, text="Echo / Delay"); f3.pack(fill='x', **pad)
    ttk.Checkbutton(f3, text="Enable", variable=v['echo']).pack(anchor='w', padx=6)
    slider(f3, "Time", v['echo_time'], 0.05, 0.9, "{:.2f} s")
    slider(f3, "Feedback", v['echo_fb'], 0.0, 0.9)
    slider(f3, "Mix", v['echo_mix'], 0.0, 1.0)

    # Chorus + pitch
    f4 = ttk.Labelframe(root, text="Chorus & Pitch"); f4.pack(fill='x', **pad)
    ttk.Checkbutton(f4, text="Chorus", variable=v['chorus']).pack(anchor='w', padx=6)
    slider(f4, "Chorus mix", v['chorus_mix'], 0.0, 1.0)
    slider(f4, "Pitch (semi)", v['pitch_semi'], -12, 12, "{:.1f}")

    # Auto-tune
    f5 = ttk.Labelframe(root, text="Auto-Tune"); f5.pack(fill='x', **pad)
    r5 = ttk.Frame(f5); r5.pack(fill='x')
    ttk.Checkbutton(r5, text="Enable", variable=v['autotune']).pack(side='left', padx=6)
    ttk.Label(r5, text="Key").pack(side='left', padx=(10, 2))
    ttk.Combobox(r5, textvariable=v['at_key'], values=NOTE_NAMES, state='readonly', width=4).pack(side='left')
    ttk.Label(r5, text="Scale").pack(side='left', padx=(10, 2))
    ttk.Combobox(r5, textvariable=v['at_scale'], values=list(dsp.SCALES), state='readonly', width=11).pack(side='left')
    lbl_note = ttk.Label(r5, text="♪ --", font=('Segoe UI', 11, 'bold'))
    lbl_note.pack(side='right', padx=8)
    slider(f5, "Strength", v['at_strength'], 0.0, 1.0)
    slider(f5, "Retune speed", v['at_retune'], 0.02, 1.0)

    def apply_preset(name):
        base = dict(DEFAULT_SETTINGS)
        base.update(PRESETS[name])
        v['monitor_db'].set(base['monitor_db']); v['lowcut'].set(base['lowcut'])
        v['gate'].set(base['gate']); v['gate_thresh'].set(base['gate_thresh'])
        v['comp'].set(base['comp']); v['reverb'].set(base['reverb'])
        v['reverb_room'].set(base['reverb_room']); v['reverb_wet'].set(base['reverb_wet'])
        v['echo'].set(base['echo']); v['echo_time'].set(base['echo_time'])
        v['echo_fb'].set(base['echo_fb']); v['echo_mix'].set(base['echo_mix'])
        v['chorus'].set(base['chorus']); v['chorus_mix'].set(base['chorus_mix'])
        v['pitch_semi'].set(base['pitch_semi']); v['autotune'].set(base['autotune'])
        v['at_key'].set(NOTE_NAMES[base['at_key']]); v['at_scale'].set(base['at_scale'])
        v['at_strength'].set(base['at_strength']); v['at_retune'].set(base['at_retune'])

    for name in PRESETS:
        ttk.Button(pf, text=name, command=lambda n=name: apply_preset(n)).pack(side='left', padx=2)

    status = ttk.Label(root, text="Stopped", anchor='w', relief='sunken',
                       font=('Consolas', 9))
    status.pack(fill='x', side='bottom')

    def do_start():
        if engine.running:
            engine.stop()
            btn_start.config(text="▶  START")
            status.config(text="Stopped", foreground=T['dim'])
            return
        try:
            in_i = in_idx_map[in_labels.index(v_in.get())]
            out_i = out_idx_map[out_labels.index(v_out.get())]
        except ValueError:
            messagebox.showerror("Device", "Pick a valid input and output device.")
            return
        blk = LATENCY_PRESETS[v_lat.get()]
        sync()
        try:
            engine.start(in_i, out_i, blk, exclusive=v_excl.get())
        except Exception as e:
            messagebox.showerror("Audio error",
                                 f"Could not start the audio stream:\n\n{e}\n\n"
                                 "Try turning off Exclusive mode, picking a different "
                                 "device, a Safe latency, or closing other audio apps.")
            return
        btn_start.config(text="■  STOP")

    btn_start.config(command=do_start)

    def restyle():
        T.clear(); T.update(thm.tokens)
        theme.apply_styles(style, root, T)
        banner.config(bg=T['panel2'], fg=T['warn'])
        upd_bar.config(bg=T['panel2'])
        upd_lbl.config(bg=T['panel2'], fg=T['acc2'])
        status.config(background=T['panel'], foreground=T['dim'])
        if not engine.running:
            lbl_note.config(foreground=T['acc2'])
        btn_theme.config(text=("☀" if thm.mode == 'dark' else "☾"))

    def toggle_theme():
        thm.toggle_mode(); restyle(); thm.save()

    def open_accent():
        theme.AccentPicker(root, thm, lambda hx: (thm.set_accent(hx), restyle()))

    btn_theme.config(command=toggle_theme)
    btn_accent.config(command=open_accent)
    restyle()

    def restart_if_running(*_):
        if engine.running:
            engine.stop()
            do_start()
    cb_in.bind('<<ComboboxSelected>>', restart_if_running)
    cb_out.bind('<<ComboboxSelected>>', restart_if_running)
    cb_lat.bind('<<ComboboxSelected>>', restart_if_running)
    chk_excl.config(command=restart_if_running)

    def poll():
        st = engine.status()
        lbl_note.config(text=f"♪ {st['note']}")
        if st['running']:
            msg = (f"● LIVE [{st['mode']}]   {st['sr']} Hz   CPU {st['cpu']*100:4.1f}%   "
                   f"round-trip ~{st['latency']*1000:4.0f} ms   xruns {st['xruns']}")
            if st['error']:
                msg += f"   ERR {st['error']}"
                status.config(text=msg, foreground=T['err'])
            else:
                status.config(text=msg, foreground=T['acc2'])
        root.after(120, poll)
    poll()

    def on_close():
        engine.stop()
        root.destroy()
    root.protocol("WM_DELETE_WINDOW", on_close)
    if os.environ.get('KARAOKE_TOPMOST'):
        try:
            root.attributes('-topmost', True)
            root.geometry('+30+20')
            root.lift()
        except Exception:
            pass
    _sc = os.environ.get('KARAOKE_SELFCLOSE')
    if _sc:
        root.after(int(_sc), on_close)
    root.mainloop()


if __name__ == '__main__':
    if '--list' in sys.argv:
        print(sd.query_devices())
    else:
        run_gui()
