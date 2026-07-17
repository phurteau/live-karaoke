# 🎤 Live Karaoke

Turn your PC microphone into a live karaoke machine. Your voice is captured, run
through studio effects, and played back **in real time** through your
headphones - **reverb, echo, chorus, pitch shift, and real auto-tune** - with a
dark, green-accented GUI.

Windows • Python • [sounddevice](https://python-sounddevice.readthedocs.io) +
[pedalboard](https://spotify.github.io/pedalboard/)

---

## ⚠️ Use wired headphones

This app plays your live voice back to you. Two rules:

- **Headphones, not speakers** - on speakers the mic re-captures the output and
  you get a feedback howl (a limiter guards your ears, but still).
- **Wired, not Bluetooth** - Bluetooth adds 150–250 ms of unavoidable delay that
  no app can remove. For live monitoring you want a **wired** headset.

---

## Quick start

```bat
git clone https://github.com/phurteau/live-karaoke.git
cd live-karaoke
run_karaoke.bat
```

The first run of **`run_karaoke.bat`** automatically creates a virtual
environment and installs the dependencies (needs **Python 3.9+** on your PATH -
get it from [python.org](https://www.python.org/downloads/) and tick *“Add
python.exe to PATH”*). Every later run just launches the app.

Prefer to do it by hand?

```bat
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python karaoke.py
```

---

## Using it

1. Pick your **Mic in** and **Output** (your headphones). **WASAPI** devices are
   auto-selected because they give the lowest latency.
2. Set **Latency** - *Ultra (128)* is the default and lowest; if you hear
   crackles, step up to *Low / Balanced / Safe*. Watch the **xruns** counter in
   the status bar (it should stay `0`).
3. Tick **☑ Exclusive mode** for the lowest possible latency (bypasses the
   Windows audio mixer). Leave it off if it won’t engage on your hardware.
4. Click **▶ START**, put your headphones on, and sing.
5. Try the **Presets**, then tweak the sliders to taste.

The status bar reports the live mode, sample rate, CPU, **round-trip latency in
ms**, and dropout (xrun) count, e.g.
`● LIVE [WASAPI exclusive 128] 48000 Hz  CPU 3.1%  round-trip ~11 ms  xruns 0`.

---

## About latency

Live monitoring latency comes almost entirely from the **audio I/O path**, not
the effects (the effects are zero-added-latency). Typical round-trip:

| Setup | Round-trip |
|-------|-----------|
| Bluetooth headphones | 150–250 ms ❌ (unusable - go wired) |
| WASAPI shared, wired | ~30–50 ms |
| WASAPI exclusive, wired, Ultra | ~10–20 ms ✅ |

Want **true zero-latency** dry monitoring (no effects)? Windows has a built-in
option: **Settings → System → Sound → More sound settings → Recording → your mic
→ Properties → Listen → ☑ “Listen to this device.”** That’s instant but has no
reverb/auto-tune. This app is the trade: a few ms of latency in exchange for
live effects. For studio-grade latency, an external **ASIO** audio interface is
the next step up.

---

## Effects

- **Voice cleanup** - low-cut (removes rumble), compressor (evens out level),
  noise gate (kills background hiss between phrases).
- **Reverb** - room size + amount (bathroom → concert hall).
- **Echo / Delay** - time, feedback, mix.
- **Chorus** - thickens / doubles the voice.
- **Pitch** - shift your whole voice up/down ±12 semitones (chipmunk / deep).
- **Auto-Tune** - snaps your pitch to a musical **Key** + **Scale**.
  - *Strength* 1.0 = hard, robotic T-Pain tuning; lower = gentle correction.
  - *Retune speed* high = instant snapping; low = smooth glide.
  - The live **♪ note** readout shows the note it’s hearing.

**Presets:** Clean · Karaoke · Concert Hall · T-Pain · Robot · Chipmunk · Deep Voice.

---

## How it works

- **I/O:** `sounddevice` full-duplex stream (mic → speakers) with a small block
  size; WASAPI shared by default, exclusive on request.
- **Effects:** Spotify’s `pedalboard` (Reverb, Delay, Chorus, Compressor,
  NoiseGate, Highpass, Gain, Limiter) - all zero-added-latency, processed live.
- **Pitch / Auto-Tune:** a **custom time-domain pitch shifter** (`dsp.py`).
  `pedalboard`’s built-in PitchShift sounds great but buffers ~1.08 s (fine
  offline, unusable live), so pitch is done with a delay-line shifter that is
  1:1 real-time, accurate to <1%, and ~1% CPU. Pitch is detected with FFT
  autocorrelation and snapped to the chosen scale.

---

## Files

| File | Purpose |
|------|---------|
| `karaoke.py` | Audio engine + Tkinter GUI |
| `dsp.py` | Pitch shifter, pitch detection, scale / auto-tune math |
| `theme.py` | Token-based dark/light themes + HSV accent color-wheel picker |
| `updater.py` | Checks GitHub Releases and applies in-app updates |
| `selftest.py` | Offline test of every effect path (no mic needed) |
| `run_karaoke.bat` | Launcher (auto-installs on first run) |
| `uninstall.bat` | Removes the venv, or optionally the whole folder |
| `requirements.txt` | Python dependencies |

Run the offline self-test any time:

```bat
.venv\Scripts\python selftest.py
```

---

## Troubleshooting

- **~1 second echo** - you’re almost certainly on **Bluetooth**. Switch to wired
  headphones.
- **Still slappy on wired** - tick **Exclusive mode**; if the reported round-trip
  won’t drop below ~40 ms your onboard codec may be the floor (use the Windows
  “Listen to this device” monitor for dry zero-latency).
- **“Could not start the audio stream”** - another app may own the mic, or
  exclusive mode was refused. Untick Exclusive, pick a different device, or use a
  Safe latency.
- **Crackles / dropouts** - raise the Latency setting and close other audio apps;
  keep an eye on the **xruns** counter.
- **Too quiet / too loud** - use the **Monitor vol** slider.
- **List devices from a terminal:** `.venv\Scripts\python karaoke.py --list`

---

## Uninstall

Run **`uninstall.bat`** - it removes the virtual environment (and can optionally
delete the whole folder). Re-running `run_karaoke.bat` rebuilds everything.

## Themes & accent color

The UI is a **token-based dual theme**: **dark** (true black, default) or **light**
(soft off-white), toggled with the **☀/☾** button in the header. A single
user-chosen **accent** color drives every highlight - the START button, section
titles, checkboxes, focus rings and the color-wheel marker - while every other
surface stays neutral, so any accent looks good.

Click **🎨 Color** to open an **HSV color-wheel picker**: drag on the wheel
(hue = angle, saturation = distance from center), set **Brightness** below, or
type a **hex** value. Changes apply live. A companion "brighter" shade for hovers
and glows, plus readable text color on accent buttons, are derived automatically.
Your theme and accent persist between runs (default: dark + a dimmed green
`#025500`).

## Automatic updates

On launch, the app quietly checks GitHub for a newer release. If one exists, a
green **🔔 New version available** banner appears at the top with a one-click
**⬇ Update now** button:

- If you installed via `git clone`, it updates in place with `git pull`
  (falling back to the release zip if needed).
- If you installed from a downloaded zip, it downloads and extracts the latest
  release over your copy.

Dependencies are synced automatically, then you're prompted to **restart** to
apply. The check is non-blocking and fails silently when you're offline. Use the
**✕** to dismiss the banner, or **Release notes** to view the changelog on
GitHub.

## License

[MIT](LICENSE)
