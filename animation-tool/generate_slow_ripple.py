#!/usr/bin/env python3
"""
Generate a slow-motion ripple animation for the SunMirror hexagonal display.

Timing:
  Each animation keyframe → 1 path-frame (step_size=1.0, tiny delta < 1°)
  Each path-frame sleeps frame_delay_ms via the new play_frame_path parameter.
  So: total_frames × frame_delay_ms = target_duration_ms

Design:
  Phase 1 – EXPAND (2 min, outward ripple): 90° → 180°
    Ring 0 (sectors 1-6)   starts first
    Ring 1 (sectors 7-24)  starts at 1/3 of phase duration
    Ring 2 (sectors 25-54) starts at 2/3 of phase duration
    All rings reach 180° simultaneously at end of phase.

  Phase 2 – RETRACT (4 min, inward ripple): 180° → 0°
    Ring 2 (outer) starts first (reverses the wave)
    Ring 1 starts at 1/3 of phase duration
    Ring 0 starts at 2/3 of phase duration
    All rings reach 0° simultaneously at end of phase.

  End: brief hold at 0°, then all return to 90° (for loop continuity).
"""

import json
import math
import os

# ── Sector layout ─────────────────────────────────────────────────────────────
RING_0 = [str(i) for i in range(1, 7)]    # center  (6 sectors)
RING_1 = [str(i) for i in range(7, 25)]   # middle  (18 sectors)
RING_2 = [str(i) for i in range(25, 55)]  # outer   (30 sectors)
RINGS  = [RING_0, RING_1, RING_2]

# ── Timing ────────────────────────────────────────────────────────────────────
FRAME_DELAY_MS   = 20          # per-path-frame sleep (controlled by main.py)
EXPAND_MINUTES   = 2
RETRACT_MINUTES  = 4
STAGGER_FRACTION = 1 / 3      # each ring starts this fraction into the phase

# Derived
EXPAND_FRAMES    = int(EXPAND_MINUTES  * 60 * 1000 / FRAME_DELAY_MS)   # 6000
RETRACT_FRAMES   = int(RETRACT_MINUTES * 60 * 1000 / FRAME_DELAY_MS)   # 12000

START_ANGLE = 90.0
PEAK_ANGLE  = 180.0
TROUGH_ANGLE = 0.0


def make_frame(fid, ring_angles):
    """Build one animation keyframe."""
    angles = {}
    for ring, angle in zip(RINGS, ring_angles):
        for sec in ring:
            angles[sec] = round(float(angle), 3)
    return {"id": fid, "angles": angles}


def generate():
    frames = []

    def emit(ring_angles, count=1):
        for _ in range(count):
            frames.append(make_frame(len(frames), ring_angles))

    # Per-ring target angle progression across a phase:
    # ring_i starts at tick = stagger_fraction * i * total_ticks
    # and linearly interpolates from src to dst, arriving simultaneously at end.
    def phase_angles(tick, total_ticks, src, dst, reverse_order=False):
        """Return [angle_ring0, angle_ring1, angle_ring2] for this tick."""
        angles = []
        for i in range(3):
            ring_i = (2 - i) if reverse_order else i
            start_tick = int(STAGGER_FRACTION * ring_i * total_ticks)
            if tick < start_tick:
                angles.append(src)
            else:
                progress = min(1.0, (tick - start_tick) / (total_ticks - start_tick))
                angles.append(src + (dst - src) * progress)
        return angles

    # ── Phase 1: EXPAND ───────────────────────────────────────────────────────
    for t in range(EXPAND_FRAMES):
        emit(phase_angles(t, EXPAND_FRAMES, START_ANGLE, PEAK_ANGLE))

    # Brief hold at peak (0.5s)
    emit([PEAK_ANGLE] * 3, int(500 / FRAME_DELAY_MS))

    # ── Phase 2: RETRACT ──────────────────────────────────────────────────────
    for t in range(RETRACT_FRAMES):
        emit(phase_angles(t, RETRACT_FRAMES, PEAK_ANGLE, TROUGH_ANGLE, reverse_order=True))

    # Brief hold at trough (0.5s)
    emit([TROUGH_ANGLE] * 3, int(500 / FRAME_DELAY_MS))

    # Return smoothly to neutral (1s)
    return_frames = int(1000 / FRAME_DELAY_MS)
    for t in range(return_frames):
        progress = t / return_frames
        angle = TROUGH_ANGLE + (START_ANGLE - TROUGH_ANGLE) * progress
        emit([angle] * 3)

    emit([START_ANGLE] * 3, 5)  # final hold

    # ── Inject timing metadata into first frame ───────────────────────────────
    frames[0]['frame_delay_ms'] = FRAME_DELAY_MS

    total_ms = len(frames) * FRAME_DELAY_MS
    total_min = total_ms / 60000
    print(f"Generated {len(frames)} keyframes")
    print(f"Expand:  {EXPAND_FRAMES} frames = {EXPAND_FRAMES * FRAME_DELAY_MS / 60000:.2f} min")
    print(f"Retract: {RETRACT_FRAMES} frames = {RETRACT_FRAMES * FRAME_DELAY_MS / 60000:.2f} min")
    print(f"Total duration: ~{total_min:.2f} min  ({total_ms/1000:.0f}s)")

    return frames


if __name__ == '__main__':
    frames = generate()

    out_dir  = os.path.join(os.path.dirname(__file__), 'animations')
    out_path = os.path.join(out_dir, 'Slow Ripple Wave.json')
    os.makedirs(out_dir, exist_ok=True)

    with open(out_path, 'w') as f:
        json.dump(frames, f, separators=(',', ':'))

    size_kb = os.path.getsize(out_path) / 1024
    print(f"Saved → {out_path}  ({size_kb:.0f} KB)")
