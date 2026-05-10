"""
Figure 3: Computational overhead of access control token derivation between
one initiating agent and 1, 10, and 100 receiving agents, varying by token
lifetime (L).

Methodology: each token requires one DH exchange + HKDF + AES-GCM encrypt +
AES-GCM decrypt.  Over a 1-day window the number of tokens = (86400 / L) * N.
"""
import sys, os, time, base64, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "saga"))

import numpy as np
import matplotlib.pyplot as plt
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

# ── Parameters matching the paper ────────────────────────────────────────────
N_RECEIVERS   = [1, 10, 100]
WINDOW_SECS   = 86400   # 1 day

# Token lifetimes in seconds (1 min, 3 min, 6 min, 12 min, 1 hr, 8 hr, 1 day)
LIFETIME_SECS   = [60, 3*60, 6*60, 12*60, 3600, 8*3600, 86400]
LIFETIME_LABELS = ["1 min", "3 min", "6 min", "12 min", "1 hr", "8 hrs", "1 day"]

BENCH_REPS = 20   # repetitions to get a stable per-token time

# ── Single-token benchmark ────────────────────────────────────────────────────
def _make_token_payload() -> dict:
    """Build a realistic token dict (matches Agent.generate_token)."""
    from datetime import datetime, timezone, timedelta
    from cryptography.hazmat.primitives.asymmetric import x25519 as _x
    pac_priv = _x.X25519PrivateKey.generate()
    return {
        "nonce": os.urandom(12),
        "issue_timestamp": datetime.now(timezone.utc),
        "expiration_timestamp": datetime.now(timezone.utc) + timedelta(hours=1),
        "communication_quota": 50,
        "recipient_pac": pac_priv.public_key(),
    }

def bench_one_token(reps: int = BENCH_REPS) -> float:
    """Return mean wall-clock time (seconds) for a full DH + HKDF + enc + dec cycle."""
    from cryptography.hazmat.primitives import serialization

    def _enc(token_dict, key):
        nonce = token_dict["nonce"]
        payload = json.dumps({
            "nonce": base64.b64encode(nonce).decode(),
            "issue_timestamp": token_dict["issue_timestamp"].isoformat(),
            "expiration_timestamp": token_dict["expiration_timestamp"].isoformat(),
            "communication_quota": token_dict["communication_quota"],
            "recipient_pac": base64.b64encode(
                token_dict["recipient_pac"].public_bytes(
                    encoding=serialization.Encoding.Raw,
                    format=serialization.PublicFormat.Raw
                )
            ).decode()
        }).encode()
        cipher = Cipher(algorithms.AES(key), modes.GCM(nonce))
        enc = cipher.encryptor()
        ct  = enc.update(payload) + enc.finalize()
        return nonce + ct + enc.tag

    def _dec(blob, key):
        nonce, ct, tag = blob[:12], blob[12:-16], blob[-16:]
        cipher = Cipher(algorithms.AES(key), modes.GCM(nonce, tag))
        dec = cipher.decryptor()
        return dec.update(ct) + dec.finalize()

    times = []
    for _ in range(reps):
        # --- initiating side keys ---
        i_priv = x25519.X25519PrivateKey.generate()
        i_pub  = i_priv.public_key()
        # --- receiving side OTK ---
        r_otk_priv = x25519.X25519PrivateKey.generate()
        r_otk_pub  = r_otk_priv.public_key()

        t0 = time.perf_counter()
        # DH (initiating side)
        dh_i = i_priv.exchange(r_otk_pub)
        # DH (receiving side)
        dh_r = r_otk_priv.exchange(i_pub)
        # HKDF
        sdhk = HKDF(algorithm=hashes.SHA256(), length=32,
                    salt=None, info=b"access-control-shdk-exchange").derive(dh_i)
        # Encrypt token
        tok = _make_token_payload()
        blob = _enc(tok, sdhk)
        # Validate shared key symmetry + decrypt
        sdhk_r = HKDF(algorithm=hashes.SHA256(), length=32,
                       salt=None, info=b"access-control-shdk-exchange").derive(dh_r)
        _dec(blob, sdhk_r)
        times.append(time.perf_counter() - t0)

    return float(np.mean(times))

# ── Total overhead computation ────────────────────────────────────────────────
print("Benchmarking per-token derivation …", flush=True)
per_token_sec = bench_one_token()
print(f"  Per-token time: {per_token_sec*1000:.3f} ms")

results = {}
for n in N_RECEIVERS:
    row = []
    for L in LIFETIME_SECS:
        n_tokens  = (WINDOW_SECS / L) * n
        total     = per_token_sec * n_tokens
        row.append(total)
    results[n] = row

# ── Plot ──────────────────────────────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(7, 4))

markers = ['o', 's', 'D']
for idx, n in enumerate(N_RECEIVERS):
    ax.plot(LIFETIME_LABELS, results[n],
            marker=markers[idx], label=str(n), linewidth=1.5)

ax.set_xlabel("Token Lifetime (L)", fontsize=11)
ax.set_ylabel("Computational Overhead (sec)", fontsize=11)
ax.legend(title="Receiving Agents", fontsize=9)
ax.set_ylim(bottom=0)
ax.grid(True, linestyle="--", alpha=0.4)
fig.tight_layout()

out = os.path.join(os.path.dirname(__file__), "fig3_token_derivation.pdf")
fig.savefig(out, dpi=150)
print(f"Saved → {out}")
plt.close(fig)
