"""
Figure 2: Computational overhead of OTK generation for the user,
as a function of frequency and key-chain length.

Replicates the methodology from Section VI-B of the SAGA paper.
Each "event" generates N X25519 keypairs and signs each with Ed25519.
The total cost is computed over an 8-hour window.
"""
import sys, os, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "saga"))

import numpy as np
import matplotlib.pyplot as plt
from cryptography.hazmat.primitives.asymmetric import x25519, ed25519

# ── Parameters matching the paper ────────────────────────────────────────────
OTK_COUNTS      = [10, 100, 1000]
WINDOW_HOURS    = 8
WINDOW_SECS     = WINDOW_HOURS * 3600

# Frequencies expressed as seconds between generation events
FREQ_LABELS   = ["every\n5 min", "10 min", "15 min", "30 min", "1 hr", "8 hrs"]
FREQ_INTERVALS = [5*60, 10*60, 15*60, 30*60, 60*60, 8*3600]

BENCH_REPS = 5   # repetitions per (n_otks) measurement for stability

# ── Benchmark a single batch of N OTKs ───────────────────────────────────────
def bench_batch(n_otks: int, reps: int = BENCH_REPS) -> float:
    """Return mean wall-clock time (seconds) to generate one batch of n_otks."""
    signing_key = ed25519.Ed25519PrivateKey.generate()
    times = []
    for _ in range(reps):
        t0 = time.perf_counter()
        for _ in range(n_otks):
            priv = x25519.X25519PrivateKey.generate()
            pub  = priv.public_key()
            pub_bytes = pub.public_bytes_raw()
            signing_key.sign(pub_bytes)
        times.append(time.perf_counter() - t0)
    return float(np.mean(times))

# ── Compute total overhead over 8 hours ──────────────────────────────────────
def total_overhead(n_otks: int, interval_secs: int) -> float:
    """Total cost (s) of generating OTKs every `interval_secs` for 8 hours."""
    n_events    = max(1, WINDOW_SECS // interval_secs)
    per_batch   = bench_batch(n_otks)
    return per_batch * n_events

# ── Run and collect data ──────────────────────────────────────────────────────
print("Benchmarking OTK generation (Fig 2) …")
results = {}   # results[n_otks][freq_idx] = total_overhead_secs

for n in OTK_COUNTS:
    print(f"  N={n} OTKs …", flush=True)
    row = []
    for interval in FREQ_INTERVALS:
        oh = total_overhead(n, interval)
        row.append(oh)
        print(f"    interval={interval//60}min  overhead={oh:.3f}s")
    results[n] = row

# ── Plot ──────────────────────────────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(7, 4))

markers = ['o', 's', 'D']
for idx, n in enumerate(OTK_COUNTS):
    ax.plot(FREQ_LABELS, results[n],
            marker=markers[idx], label=f"{n}", linewidth=1.5)

ax.set_xlabel("OTK Generation Frequency", fontsize=11)
ax.set_ylabel("Computational Overhead (sec)", fontsize=11)
ax.legend(title="Number of OTKs", fontsize=9)
ax.set_ylim(bottom=0)
ax.grid(True, linestyle="--", alpha=0.4)
fig.tight_layout()

out = os.path.join(os.path.dirname(__file__), "fig2_otk_generation.pdf")
fig.savefig(out, dpi=150)
print(f"\nSaved → {out}")
plt.close(fig)
