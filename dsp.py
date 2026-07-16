"""DSP building blocks for the live karaoke app.

- TDPitchShifter: low-latency time-domain (delay-line) pitch shifter for voice.
- detect_pitch:   FFT-autocorrelation fundamental-frequency estimator.
- Scale/auto-tune helpers.

pedalboard's PitchShift has a fixed ~1.08 s latency (great offline, unusable
live), so pitch shift + auto-tune are done here with a custom shifter that is
1:1 real time, accurate, and cheap.
"""
import numpy as np

# ---------------------------------------------------------------- pitch shift
class TDPitchShifter:
    """Time-domain delay-line pitch shifter (two crossfading read taps sweeping
    a ring buffer). Latency averages ~grain/2 samples; output length == input
    length. Ideal for the small corrections used by auto-tune (near-zero
    artifacts) and usable for larger creative shifts."""

    def __init__(self, grain=1536, buflen=16384):
        self.W = int(grain)
        self.buflen = int(buflen)
        self.buf = np.zeros(self.buflen, dtype=np.float32)
        self.wpos = 0
        self.phase = 0.0

    def reset(self):
        self.buf[:] = 0.0
        self.wpos = 0
        self.phase = 0.0

    def process(self, x, ratio):
        """Shift block x by frequency `ratio` (out_freq = ratio * in_freq)."""
        n = len(x)
        if abs(ratio - 1.0) < 1e-4:
            # transparent path: still fill the buffer so state stays coherent
            widx = (self.wpos + np.arange(n)) % self.buflen
            self.buf[widx] = x
            self.wpos = int((self.wpos + n) % self.buflen)
            return x.astype(np.float32, copy=True)

        W = self.W
        L = self.buflen
        buf = self.buf
        idx = np.arange(n)
        widx = (self.wpos + idx) % L
        buf[widx] = x
        wpos_arr = (self.wpos + idx).astype(np.float64)

        dphase = (1.0 - ratio) / W
        phase = self.phase + idx * dphase
        phase0 = phase % 1.0
        phase1 = (phase + 0.5) % 1.0
        d0 = phase0 * W
        d1 = phase1 * W

        def read(rp):
            rp = rp % L
            i0 = np.floor(rp).astype(np.int64) % L
            frac = (rp - np.floor(rp)).astype(np.float32)
            i1 = (i0 + 1) % L
            return buf[i0] * (1.0 - frac) + buf[i1] * frac

        s0 = read(wpos_arr - d0)
        s1 = read(wpos_arr - d1)
        w0 = (0.5 - 0.5 * np.cos(2 * np.pi * phase0)).astype(np.float32)
        w1 = (0.5 - 0.5 * np.cos(2 * np.pi * phase1)).astype(np.float32)
        out = (w0 * s0 + w1 * s1).astype(np.float32)

        self.wpos = int((self.wpos + n) % L)
        self.phase = float((self.phase + n * dphase) % 1.0)
        return out


# ------------------------------------------------------------- pitch detection
def detect_pitch(x, sr, fmin=75.0, fmax=1000.0, rms_gate=1e-3):
    """Estimate fundamental frequency (Hz) via FFT autocorrelation.
    Returns 0.0 when the block is too quiet or no clear pitch is found."""
    x = x - np.mean(x)
    if np.sqrt(np.mean(x * x)) < rms_gate:
        return 0.0
    n = len(x)
    win = x * np.hanning(n)
    f = np.fft.rfft(win, 2 * n)
    ac = np.fft.irfft(f * np.conj(f))[:n]
    lag_min = max(1, int(sr / fmax))
    lag_max = min(int(sr / fmin), n - 1)
    if lag_max <= lag_min:
        return 0.0
    seg = ac[lag_min:lag_max]
    peak = int(np.argmax(seg)) + lag_min
    if ac[peak] <= 0 or ac[peak] < 0.30 * ac[0]:
        return 0.0  # weak periodicity -> treat as unvoiced
    if 1 <= peak < n - 1:
        a, b, c = ac[peak - 1], ac[peak], ac[peak + 1]
        denom = (a - 2 * b + c)
        if denom != 0:
            peak = peak + 0.5 * (a - c) / denom
    if peak <= 0:
        return 0.0
    return sr / peak


# --------------------------------------------------------------- scale helpers
NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

SCALES = {
    'chromatic': {0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11},
    'major':     {0, 2, 4, 5, 7, 9, 11},
    'minor':     {0, 2, 3, 5, 7, 8, 10},
    'pentatonic':{0, 2, 4, 7, 9},
}


def hz_to_midi(f):
    return 69.0 + 12.0 * np.log2(f / 440.0)


def midi_to_hz(m):
    return 440.0 * 2.0 ** ((m - 69.0) / 12.0)


def note_name(f):
    if f <= 0:
        return '--'
    m = int(round(hz_to_midi(f)))
    return f"{NOTE_NAMES[m % 12]}{m // 12 - 1}"


def autotune_ratio(f, key_pc, scale_name, strength):
    """Pitch ratio that snaps detected freq f to the nearest note of the given
    key/scale, scaled by strength (0=off, 1=hard tune)."""
    if f <= 0:
        return 1.0
    allowed = {(pc + key_pc) % 12 for pc in SCALES.get(scale_name, SCALES['chromatic'])}
    m = hz_to_midi(f)
    base = int(np.floor(m))
    best, bestd = None, 1e9
    for cand in range(base - 2, base + 3):
        if cand % 12 in allowed:
            d = abs(cand - m)
            if d < bestd:
                bestd, best = d, cand
    if best is None:
        return 1.0
    corrected = m + (best - m) * float(strength)
    return float(2.0 ** ((corrected - m) / 12.0))
