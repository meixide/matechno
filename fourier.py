#!/usr/bin/env python3
"""

Generate 8 harmonic stems for a classic waveform (triangle/square/saw) so that,
when played together, they approximate the target sound.

Key points:
  - Stems keep TRUE Fourier amplitudes (no per-stem normalization).
  - Only the MIX reference is normalized (so it won't clip).
  - Saves PNG plots for each stem and for the sum of 8 harmonics.

Waveforms (sine series in time domain):
  - triangle: n odd only; c_n =  8/(π^2) * (-1)^{k-1} / n^2, with n = 2k-1 (FAST convergence)
  - square:   n odd only; c_n =  4/(π n)                         (more bite, Gibbs with few terms)
  - saw:      n = 1..N;  c_n =  2/π * (-1)^{n+1} / n             (bright, least smooth with few terms)

Default output directory: /Users/cgmeixide/musik/nocheuro/fourier
"""

import argparse
import os
import math
import numpy as np
import wave
import matplotlib.pyplot as plt

# ---------- WAV IO ----------
def write_wav_int16(path: str, y: np.ndarray, sr: int, normalize: bool = False, remove_dc: bool = True) -> None:
    """
    Write mono 16-bit PCM WAV.
    - If normalize=True, scales to 95% FS.
    - If remove_dc=True, subtracts mean to reduce clicks.
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)

    if remove_dc:
        y = y - np.mean(y)

    if normalize:
        peak = np.max(np.abs(y)) if np.max(np.abs(y)) > 0 else 1.0
        y = 0.95 * y / peak

    y16 = np.clip(np.round(y * 32767.0), -32768, 32767).astype(np.int16)

    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(y16.tobytes())

# ---------- Harmonic definitions ----------
def triangle_harmonics(N_stems=8):
    """
    Triangle (sine series): n odd only; c_n = 8/(π^2) * (-1)^{k-1} / n^2, n=2k-1
    """
    n_list = [2*k-1 for k in range(1, N_stems+1)]
    c = []
    for k, n in enumerate(n_list, start=1):
        sign = (-1)**(k-1)  # +, -, +, -, ...
        c.append(sign * (8.0 / (math.pi**2)) / (n**2))
    return n_list, c

def square_harmonics(N_stems=8):
    """
    Square (sine series): n odd only; c_n = 4/(π n)
    """
    n_list = [2*k-1 for k in range(1, N_stems+1)]
    c = [(4.0 / math.pi) / n for n in n_list]
    return n_list, c

def saw_harmonics(N_stems=8):
    """
    Sawtooth (sine series): n=1..N; c_n = 2/π * (-1)^{n+1} / n
    """
    n_list = list(range(1, N_stems+1))
    c = [ (2.0 / math.pi) * ((-1)**(n+1)) / n for n in n_list ]
    return n_list, c

WAVEFORMS = {
    "triangle": triangle_harmonics,
    "square":   square_harmonics,
    "saw":      saw_harmonics,
}

# ---------- Plot helper ----------
def save_wave_plot(path: str, t: np.ndarray, y: np.ndarray, title: str):
    """
    Save a simple time-domain plot (no specific styles/colors).
    """
    plt.figure(figsize=(10, 4))
    plt.plot(t, y)
    plt.title(title)
    plt.xlabel("Time (s)")
    plt.ylabel("Amplitude")
    plt.grid(True, alpha=0.3)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()

def main():
    ap = argparse.ArgumentParser(description="Create 8 harmonic stems + plots for a classic waveform.")
    ap.add_argument("--waveform", choices=list(WAVEFORMS.keys()), default="triangle",
                    help="Target waveform (triangle recommended for fastest convergence).")
    ap.add_argument("--f0", type=float, default=110.0, help="Fundamental frequency in Hz (e.g., 110 = A2).")
    ap.add_argument("--sr", type=int, default=48000, help="Sample rate.")
    ap.add_argument("--duration", type=float, default=6.0, help="Seconds per stem (and reference mix).")
    ap.add_argument("--outdir", type=str, default="/Users/cgmeixide/musik/nocheuro/fourier",
                    help="Output directory for WAVs and PNGs.")
    ap.add_argument("--headroom", type=float, default=0.9,
                    help="Global mix headroom factor ensuring sum of |amps| ≤ headroom (prevents clipping).")
    ap.add_argument("--plot_cycles", type=float, default=2.0,
                    help="How many fundamental periods to show in the plots.")
    ap.add_argument("--remove_dc", action="store_true",
                    help="Remove DC from stems (does not change relative levels).")
    args = ap.parse_args()

    # Time vectors
    t_audio = np.arange(int(args.duration * args.sr)) / args.sr
    T0 = 1.0 / args.f0
    t_plot = np.linspace(0, args.plot_cycles * T0, 3000, endpoint=False)
    two_pi = 2.0 * math.pi

    # Harmonics and raw Fourier coefficients
    n_list, c_raw = WAVEFORMS[args.waveform](N_stems=8)

    # Global scaling to avoid clipping when summing all stems:
    # ensure sum of absolute amplitudes ≤ headroom.
    total_abs = sum(abs(a) for a in c_raw)
    scale = (args.headroom / total_abs) if total_abs > 0 else 1.0
    c = [a * scale for a in c_raw]

    print(f"Waveform: {args.waveform}")
    print("Harmonics (n) and per-stem amplitudes (after global headroom scaling, no per-stem normalization):")
    for i, (n, a) in enumerate(zip(n_list, c), start=1):
        print(f"  Stem {i:02d}: n={n:<2d}, amplitude={a:+.6f}")

    # Render stems, write WAVs (no normalization), and plot each harmonic
    y_mix_audio = np.zeros_like(t_audio, dtype=float)
    y_mix_plot  = np.zeros_like(t_plot, dtype=float)

    for i, (n, a) in enumerate(zip(n_list, c), start=1):
        # Audio stem: pure sine with correct amplitude
        y_audio = a * np.sin(two_pi * n * args.f0 * t_audio)
        fname_wav = f"{args.waveform}_n{n:02d}_stem{i:02d}.wav"
        path_wav = os.path.join(args.outdir, fname_wav)
        write_wav_int16(path_wav, y_audio, args.sr, normalize=False, remove_dc=args.remove_dc)

        # Plot for this harmonic (few periods)
        y_plot = a * np.sin(two_pi * n * args.f0 * t_plot)
        fname_png = f"{args.waveform}_n{n:02d}_stem{i:02d}_plot.png"
        path_png = os.path.join(args.outdir, fname_png)
        save_wave_plot(path_png, t_plot, y_plot,
                       title=f"{args.waveform.capitalize()} – Harmonic n={n} (stem {i:02d})")

        # Accumulate sums
        y_mix_audio += y_audio
        y_mix_plot  += y_plot

    # Write normalized reference mix (so it’s easy to audition without clipping)
    ref_mix_wav = os.path.join(args.outdir, f"{args.waveform}_mix_ref.wav")
    write_wav_int16(ref_mix_wav, y_mix_audio, args.sr, normalize=True, remove_dc=args.remove_dc)

    # Plot of sum up to 8 harmonics
    ref_mix_png = os.path.join(args.outdir, f"{args.waveform}_sum08_plot.png")
    save_wave_plot(ref_mix_png, t_plot, y_mix_plot,
                   title=f"{args.waveform.capitalize()} – Fourier sum up to 8 harmonics")

    print(f"\nWAV stems + plots written to: {args.outdir}")
    print(f"Reference mix: {ref_mix_wav}")
    print(f"Reference sum plot: {ref_mix_png}")
    print("\nTip: In Traktor use Loop mode with exact cell size (1–4 bars) and keep the Master Clock running.")

if __name__ == "__main__":
    main()
