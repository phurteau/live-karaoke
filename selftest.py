import numpy as np
import karaoke
from karaoke import KaraokeEngine, list_devices, DEFAULT_SETTINGS, PRESETS

SR = 48000
eng = KaraokeEngine()
eng.sr = SR

def block(f, n, ph):
    tt = (np.arange(n) + ph) / SR
    return (0.3 * np.sin(2 * np.pi * f * tt)).astype(np.float32)

def run(settings, label, blk=256, nb=200):
    s = dict(DEFAULT_SETTINGS); s.update(settings)
    eng.ps.reset(); eng.cur_ratio = 1.0
    bad = 0; maxamp = 0.0
    for i in range(nb):
        x = block(196.0, blk, i * blk)  # ~G3
        y = eng._process(x, s)
        if y.shape[0] != blk or np.isnan(y).any() or np.isinf(y).any():
            bad += 1
        maxamp = max(maxamp, float(np.max(np.abs(y))))
    print(f"{label:16s} ok={bad==0} note={eng.detected_note:5s} peak={maxamp:.3f}")

print("--- device enumeration ---")
ins, outs = list_devices()
print(f"inputs={len(ins)} outputs={len(outs)}")
for i, l in ins[:4]:
    print("  IN ", i, l)
for i, l in outs[:4]:
    print("  OUT", i, l)

print("--- processing paths ---")
run({}, "defaults")
run(dict(reverb=True, reverb_wet=0.5), "reverb")
run(dict(echo=True, echo_mix=0.4), "echo")
run(dict(chorus=True, chorus_mix=0.5), "chorus")
run(dict(gate=True, comp=True, lowcut=True), "cleanup")
run(dict(pitch_semi=5.0), "pitch+5")
run(dict(pitch_semi=-5.0), "pitch-5")
run(dict(autotune=True, at_key=0, at_scale='major', at_strength=1.0), "autotune")
run(dict(muted=True), "muted")
for name in PRESETS:
    run(PRESETS[name], f"preset:{name}")

# block-size robustness
for blk in (128, 256, 512, 1024):
    run(dict(autotune=True, reverb=True, echo=True, chorus=True), f"all@{blk}", blk=blk, nb=120)

print("SMOKE TEST DONE")
