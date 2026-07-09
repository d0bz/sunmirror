"""
Generate the 3 preset animation JSON files for the SunMirror button cycling.
Run from the project root: python3 generate_animations.py
"""
import json, math, os

OUT_DIR = os.path.join(os.path.dirname(__file__), "animation-tool")
N = 54          # total mirrors
CENTER = 90
AMP = 40        # ±40° from center

def mirror_ids():
    return [str(i) for i in range(1, N + 1)]

def frame(id_, angles_dict):
    return {"id": id_, "angles": {str(k): v for k, v in angles_dict.items()}}

# ── helpers ────────────────────────────────────────────────────────────────

def all_at(angle):
    return {i: angle for i in range(1, N + 1)}

def rings():
    """Return (inner[1-6], middle[7-24], outer[25-54]) as lists of int ids."""
    inner  = list(range(1, 7))
    middle = list(range(7, 25))
    outer  = list(range(25, 55))
    return inner, middle, outer


# ══════════════════════════════════════════════════════════════════════════
# ANIMATION 1 – "Sync Pulse"
# All mirrors breathe in and out together. Classic slow pulse.
# Frames: flat-out → flat-in → flat-out  (repeated via loop flag in server)
# ══════════════════════════════════════════════════════════════════════════
def make_anim1():
    frames = []
    # One full cycle: out → in → center
    steps = 30
    for i in range(steps + 1):
        t = i / steps
        angle = CENTER + AMP * math.sin(t * 2 * math.pi)
        frames.append(frame(i + 1, all_at(round(angle, 1))))
    return frames


# ══════════════════════════════════════════════════════════════════════════
# ANIMATION 2 – "Ring Ripple"
# Outer ring moves first, then middle, then inner, creating an inward ripple.
# ══════════════════════════════════════════════════════════════════════════
def make_anim2():
    inner, middle, outer = rings()
    steps = 24

    def ring_angle(step, offset):
        shifted = step - offset
        if shifted < 0:
            return CENTER
        t = shifted / steps
        return CENTER + AMP * math.sin(t * 2 * math.pi)

    frames = []
    total = steps * 3 + steps          # outer offset + middle offset + inner + tail
    for i in range(total):
        angles = {}
        for mid in outer:
            angles[mid] = round(ring_angle(i, 0), 1)
        for mid in middle:
            angles[mid] = round(ring_angle(i, steps // 2), 1)
        for mid in inner:
            angles[mid] = round(ring_angle(i, steps), 1)
        frames.append(frame(i + 1, angles))

    # Close back to center
    frames.append(frame(len(frames) + 1, all_at(CENTER)))
    return frames


# ══════════════════════════════════════════════════════════════════════════
# ANIMATION 3 – "Alternating Fan"
# Odd-numbered mirrors go out while even-numbered go in, then swap.
# Creates a shimmering, flickering fan effect.
# ══════════════════════════════════════════════════════════════════════════
def make_anim3():
    steps = 36
    frames = []
    for i in range(steps + 1):
        t = i / steps
        odd_angle  = CENTER + AMP * math.sin(t * 2 * math.pi)
        even_angle = CENTER - AMP * math.sin(t * 2 * math.pi)
        angles = {}
        for mid in range(1, N + 1):
            if mid % 2 == 1:
                angles[mid] = round(odd_angle, 1)
            else:
                angles[mid] = round(even_angle, 1)
        frames.append(frame(i + 1, angles))
    return frames


if __name__ == "__main__":
    animations = [
        ("anim-pulse.json",      make_anim1(), "Sync Pulse – all mirrors breathe together"),
        ("anim-ripple.json",     make_anim2(), "Ring Ripple – wave travels inward ring by ring"),
        ("anim-alternating.json",make_anim3(), "Alternating Fan – odd/even mirrors oppose each other"),
    ]

    for filename, frames_data, desc in animations:
        path = os.path.join(OUT_DIR, filename)
        with open(path, "w") as f:
            json.dump(frames_data, f, indent=2)
        print(f"✅ {filename}  ({len(frames_data)} frames)  — {desc}")
