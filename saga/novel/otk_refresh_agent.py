"""
OTKRefreshAgent — Novel contribution.

Subclass of Agent that adds a background thread monitoring the local OTK
pool size. When the pool drops below a configurable threshold, it
automatically generates fresh OTKs, signs them, and pushes them to the
Provider via the new /replenish_otks endpoint (provider_extension.py).

This closes the gap between the paper's design (which mentions OTK
replenishment) and the reference implementation (which has no such mechanism),
and directly mitigates the OTK exhaustion DoS demonstrated in
exploit_otk_exhaustion.py.

Usage:
    from novel.otk_refresh_agent import OTKRefreshAgent
    agent = OTKRefreshAgent(workdir, material, local_agent,
                            user_email="alice_final@mail.com",
                            user_jwt="<jwt>",
                            refresh_threshold=2,
                            refresh_batch=10)
    agent.listen()
"""
import os, sys, base64, json, time, threading, warnings
warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import requests
from saga.agent import Agent
from saga.common import crypto as sc
from saga.common.logger import Logger as logger
import saga.config as cfg
from cryptography.hazmat.primitives import serialization


class OTKRefreshAgent(Agent):
    """
    Agent with automatic background OTK replenishment.

    Extra constructor arguments:
        user_email        : email of the user who owns this agent
        user_jwt          : valid provider JWT (from login)
        user_sk           : Ed25519 private key of the user (for OTK signing)
        refresh_threshold : replenish when pool falls to or below this count
        refresh_batch     : how many fresh OTKs to generate each replenishment
        poll_interval     : seconds between pool-size checks (default 5)
    """

    def __init__(self, workdir, material, local_agent=None,
                 user_email: str = "",
                 user_jwt:   str = "",
                 user_sk            = None,
                 refresh_threshold: int = 2,
                 refresh_batch:     int = 10,
                 poll_interval:     float = 5.0):

        super().__init__(workdir, material, local_agent)

        self._user_email        = user_email
        self._user_jwt          = user_jwt
        self._user_sk           = user_sk
        self._refresh_threshold = refresh_threshold
        self._refresh_batch     = refresh_batch
        self._poll_interval     = poll_interval
        self._replenish_url     = cfg.PROVIDER_CONFIG["endpoint"] + "/replenish_otks"
        self._stop_refresh      = threading.Event()

        # MongoDB connection to check remote pool size
        from pymongo import MongoClient as _MC
        self._agents_col = _MC("mongodb://localhost:27017/saga")["saga"]["agents"]

        # Start background monitor thread
        self._refresh_thread = threading.Thread(
            target=self._otk_monitor_loop, daemon=True)
        self._refresh_thread.start()
        logger.log("OTK-REFRESH",
                   f"Background OTK monitor started "
                   f"(threshold={refresh_threshold}, batch={refresh_batch}).")

    def _remote_pool_size(self) -> int:
        """Check how many OTKs remain in the provider's MongoDB pool."""
        doc = self._agents_col.find_one({"aid": self.aid}, {"one_time_keys": 1})
        return len(doc.get("one_time_keys", [])) if doc else 0

    # ── Background monitor ────────────────────────────────────────────────────
    def _otk_monitor_loop(self):
        while not self._stop_refresh.is_set():
            pool_size = self._remote_pool_size()

            if pool_size <= self._refresh_threshold:
                logger.log("OTK-REFRESH",
                           f"Pool low ({pool_size} OTKs). Replenishing...")
                try:
                    added = self._replenish_otks(self._refresh_batch)
                    logger.log("OTK-REFRESH",
                               f"Replenished {added} OTKs. "
                               f"New pool size: {pool_size + added}.")
                except Exception as e:
                    logger.error(f"OTK replenishment failed: {e}")

            self._stop_refresh.wait(self._poll_interval)

    # ── Replenishment logic ───────────────────────────────────────────────────
    def _replenish_otks(self, n: int) -> int:
        """
        Generate n fresh X25519 OTK pairs, sign each public key with the
        user's Ed25519 key, push them to the provider, and inject the
        private halves into the local otks_dict.
        Returns the number of OTKs successfully added.
        """
        if self._user_sk is None:
            raise ValueError("user_sk required for OTK replenishment.")

        new_priv_keys = []
        new_pub_b64   = []
        new_sig_b64   = []

        for _ in range(n):
            priv, pub = sc.generate_x25519_keypair()
            pub_bytes = pub.public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw)
            sig = self._user_sk.sign(pub_bytes)
            new_priv_keys.append((priv, pub_bytes))
            new_pub_b64.append(base64.b64encode(pub_bytes).decode())
            new_sig_b64.append(base64.b64encode(sig).decode())

        payload = {
            "uid":      self._user_email,
            "jwt":      self._user_jwt,
            "aid":      self.aid,
            "otks":     new_pub_b64,
            "otk_sigs": new_sig_b64,
        }
        resp = requests.post(self._replenish_url, json=payload,
                             verify=False,
                             cert=(self.workdir + "agent.crt",
                                   self.workdir + "agent.key"))

        if resp.status_code != 200:
            raise RuntimeError(f"Provider rejected replenishment: {resp.json()}")

        added = resp.json().get("added", 0)

        # Inject private keys into local pool
        with self.otks_lock:
            for priv, pub_bytes in new_priv_keys[:added]:
                self.otks_dict[pub_bytes] = priv

        return added

    def stop(self):
        """Signal the background monitor to exit cleanly."""
        self._stop_refresh.set()
