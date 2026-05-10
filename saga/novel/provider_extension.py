"""
Provider Extension — adds /replenish_otks endpoint.

This is a drop-in replacement runner for the SAGA Provider that adds one
new endpoint without touching the original provider.py.

The /replenish_otks endpoint allows an authenticated user to push fresh
OTKs into their agent's pool at the provider, enabling automatic OTK
refresh and mitigating the OTK exhaustion DoS (see exploit_otk_exhaustion.py).

Usage:
    cd /home/reward_hack/Desktop/oldsaga/saga
    source venv/bin/activate
    python novel/provider_extension.py
    (replaces: python saga/provider/provider.py)
"""
import sys, os, base64
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, ".."))                        # saga package
sys.path.insert(0, os.path.join(_HERE, "..", "saga", "provider"))    # provider.py

from flask import request, jsonify
from provider import Provider           # original Provider class
import saga.config as cfg
import saga.common.crypto as sc
from saga.common.logger import Logger as logger
from saga.common.contact_policy import check_aid
from datetime import datetime, timezone, timedelta


class ExtendedProvider(Provider):
    """
    Subclass of Provider that adds the /replenish_otks endpoint.
    No existing methods are modified.
    """

    def _register_routes(self):
        # Register all original routes first
        super()._register_routes()

        # ── New endpoint ──────────────────────────────────────────────────────
        @self.app.route('/replenish_otks', methods=['POST'])
        def replenish_otks():
            """
            Allows an authenticated agent to push fresh OTKs into its pool.

            Request body:
                uid       : user ID (email)
                jwt       : valid provider JWT
                aid       : agent ID whose pool to replenish
                otks      : list of base64-encoded new public OTK bytes
                otk_sigs  : list of base64-encoded user-signed OTK signatures

            Returns 200 on success with {"added": N}.
            """
            data = request.json
            uid      = data.get("uid")
            user_jwt = data.get("jwt")
            aid      = data.get("aid")
            new_otks     = data.get("otks", [])
            new_otk_sigs = data.get("otk_sigs", [])

            # Basic validation
            if not uid or not user_jwt or not aid:
                return jsonify({"message": "Missing uid, jwt, or aid"}), 400
            if not check_aid(aid):
                return jsonify({"message": "Invalid aid format"}), 400
            if len(new_otks) == 0:
                return jsonify({"message": "No OTKs provided"}), 400
            if len(new_otks) != len(new_otk_sigs):
                return jsonify({"message": "OTK/sig count mismatch"}), 400

            # Authenticate user
            user = self.users_collection.find_one({"uid": uid})
            if not user:
                return jsonify({"message": "User not found"}), 404

            usr_record = self.users_collection.find_one(
                {"uid": uid, "auth_tokens.token": user_jwt})
            if not usr_record:
                return jsonify({"message": "User not authenticated"}), 401

            now = datetime.now(timezone.utc)
            exp = usr_record["auth_tokens"][0]["exp"].replace(tzinfo=timezone.utc)
            if now > exp:
                return jsonify({"message": "Token expired"}), 401

            # Make sure agent belongs to this user (uid is the part before ':' in aid)
            agent = self.agents_collection.find_one({"aid": aid})
            if not agent:
                return jsonify({"message": "Agent not found"}), 404
            agent_owner = aid.split(":")[0]
            if agent_owner != uid:
                return jsonify({"message": "Agent does not belong to this user"}), 403

            # Verify OTK signatures using the user's public key
            crt_u = sc.bytesToX509Certificate(user["crt_u"])
            pk_u = crt_u.public_key()
            verified_otks  = []
            verified_sigs  = []
            for otk_b64, sig_b64 in zip(new_otks, new_otk_sigs):
                otk_bytes = base64.b64decode(otk_b64)
                sig_bytes = base64.b64decode(sig_b64)
                try:
                    pk_u.verify(sig_bytes, otk_bytes)
                    verified_otks.append(otk_b64)
                    verified_sigs.append(sig_b64)
                except Exception:
                    logger.error(f"OTK signature verification failed for {aid}.")
                    return jsonify({"message": "OTK signature verification failed"}), 403

            # Atomically append fresh OTKs to the agent's pool
            result = self.agents_collection.update_one(
                {"aid": aid},
                {"$push": {
                    "one_time_keys": {"$each": verified_otks},
                    "one_time_key_sigs": {"$each": verified_sigs}
                }}
            )
            added = len(verified_otks)
            logger.log("PROVIDER", f"Replenished {added} OTKs for agent {aid}.")
            return jsonify({"added": added}), 200


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    provider_uri = cfg.PROVIDER_CONFIG.get("endpoint")
    port = int(provider_uri.split(":")[-1])

    provider = ExtendedProvider(
        workdir="./",
        name="provider",
        host="0.0.0.0",
        port=port,
        mongo_uri="mongodb://localhost:27017/saga",
        jwt_secret="supersecretkey"
    )
    provider.run()
