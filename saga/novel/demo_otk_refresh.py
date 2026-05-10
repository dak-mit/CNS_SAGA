"""
Demo: OTK Refresh Agent in action.

Shows that OTKRefreshAgent automatically replenishes its OTK pool after
the exploit drains it, while a plain Agent would stay broken.

Steps:
  1. Start the ExtendedProvider (novel/provider_extension.py) instead of provider.py
  2. Register Alice and Bob normally
  3. Run this script — it starts Alice as an OTKRefreshAgent, then watches
     the pool refill automatically when it drops below the threshold.

Usage:
    cd /home/reward_hack/Desktop/oldsaga/saga
    source venv/bin/activate
    python novel/demo_otk_refresh.py
"""
import sys, os, base64, time, warnings
warnings.filterwarnings("ignore")

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, ".."))
sys.path.insert(0, _HERE)   # so "from novel.otk_refresh_agent" resolves

import requests, urllib3
urllib3.disable_warnings()
import saga.config as cfg
from saga.common import crypto as sc
from saga.agent import get_agent_material
from saga.common.logger import Logger as logger
from novel.otk_refresh_agent import OTKRefreshAgent

# ── Config ────────────────────────────────────────────────────────────────────
PROVIDER    = cfg.PROVIDER_CONFIG["endpoint"]
CA_CERT     = cfg.CA_CERT_PATH

ALICE_EMAIL  = "alice_final@mail.com"
ALICE_PASS   = "alice"
ALICE_AID    = "alice_final@mail.com:meeting_agent"
ALICE_WORKDIR = os.path.join(cfg.USER_WORKDIR, ALICE_AID + "/")

MALLORY_AID     = "mallory_adv@mail.com:meeting_agent"
MALLORY_WORKDIR = os.path.join(cfg.USER_WORKDIR, MALLORY_AID + "/")
MALLORY_CERT    = os.path.join(MALLORY_WORKDIR, "agent.crt")
MALLORY_KEY     = os.path.join(MALLORY_WORKDIR, "agent.key")

REFRESH_THRESHOLD = 2   # replenish when ≤ 2 OTKs remain
REFRESH_BATCH     = 5   # add 5 fresh OTKs each time

# ── Step 1: Login as Alice to get JWT and user SK ─────────────────────────────
print("[1] Logging in as Alice to get JWT...")
alice_keys_dir = os.path.join(cfg.USER_WORKDIR, "keys", ALICE_EMAIL)
alice_cert = alice_keys_dir + ".crt"
alice_key  = alice_keys_dir + ".key"
alice_sk, _ = sc.load_ed25519_keys(alice_keys_dir)

login_resp = requests.post(f"{PROVIDER}/login",
    json={"uid": ALICE_EMAIL, "password": ALICE_PASS},
    verify=False, cert=(alice_cert, alice_key))
if "access_token" not in login_resp.json():
    print(f"[!] Login failed: {login_resp.json()}")
    sys.exit(1)
alice_jwt = login_resp.json()["access_token"]
print(f"    JWT obtained: {alice_jwt[:30]}...")

# ── Step 2: Start Alice as OTKRefreshAgent ────────────────────────────────────
print(f"\n[2] Starting OTKRefreshAgent for Alice "
      f"(threshold={REFRESH_THRESHOLD}, batch={REFRESH_BATCH})...")
material = get_agent_material(ALICE_WORKDIR)
alice_agent = OTKRefreshAgent(
    workdir=ALICE_WORKDIR,
    material=material,
    local_agent=None,               # DummyAgent — no LLM needed for this demo
    user_email=ALICE_EMAIL,
    user_jwt=alice_jwt,
    user_sk=alice_sk,
    refresh_threshold=REFRESH_THRESHOLD,
    refresh_batch=REFRESH_BATCH,
    poll_interval=3.0               # check every 3 seconds
)

from pymongo import MongoClient as _MC
_agents_col = _MC("mongodb://localhost:27017/saga")["saga"]["agents"]

def get_pool_size():
    doc = _agents_col.find_one({"aid": ALICE_AID}, {"one_time_keys": 1})
    return len(doc.get("one_time_keys", [])) if doc else -1

print(f"    Initial pool size: {get_pool_size()}")

# ── Step 3: Drain Alice's pool (simulate the attack) ─────────────────────────
print(f"\n[3] Simulating OTK exhaustion attack (Mallory drains pool)...")
drained = 0
while True:
    resp = requests.post(f"{PROVIDER}/access",
        json={"i_aid": MALLORY_AID, "t_aid": ALICE_AID},
        verify=False, cert=(MALLORY_CERT, MALLORY_KEY))
    if resp.status_code != 200:
        break
    drained += 1
    print(f"    Drained OTK #{drained}. Pool now: {get_pool_size()}")

print(f"    Pool exhausted after {drained} OTKs drained.")

# ── Step 4: Watch OTKRefreshAgent replenish automatically ─────────────────────
print(f"\n[4] Watching OTKRefreshAgent auto-replenish (wait up to 15s)...")
for i in range(15):
    time.sleep(1)
    size = get_pool_size()
    print(f"    t+{i+1}s  pool size = {size}")
    if size >= REFRESH_BATCH:
        print(f"\n[+] SUCCESS: Pool refilled to {size} OTKs automatically!")
        break
else:
    print("\n[!] Pool did not refill in time — check provider_extension.py is running.")

alice_agent.stop()
print("\n[5] Demo complete.")
