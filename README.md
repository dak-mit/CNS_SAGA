# SAGA: A Security Architecture for Governing AI Agentic Systems
### Reproduction & Novel Contributions — CNS Course Project

> **Authors:** Kashvi Gupta (2023UCP1581) · Daksh Mittal (2023UCP1592)
> **Course:** Computer Networks & Security
> **Based on:** Syros et al., *SAGA: A Security Architecture for Governing AI Agentic Systems*, NDSS Symposium 2026
> **Original Paper:** https://arxiv.org/abs/2504.21034
> **Original Repository:** https://github.com/gsiros/saga

---

## Table of Contents

1. [What Is This Paper About?](#1-what-is-this-paper-about)
2. [System Architecture](#2-system-architecture)
3. [Key Security Properties](#3-key-security-properties)
4. [Repository Structure](#4-repository-structure)
5. [Setup & Installation](#5-setup--installation)
6. [Running the System](#6-running-the-system)
7. [Reproduced Evaluation Results](#7-reproduced-evaluation-results)
8. [Novel Contributions](#8-novel-contributions)
9. [Challenges Faced](#9-challenges-faced)
10. [References](#10-references)

---

## 1. What Is This Paper About?

### The Problem

Modern AI systems increasingly rely on **LLM-based agents** that autonomously plan, execute multi-step tasks, and communicate with other agents — scheduling meetings, processing expense reports, collaborating on documents, and more. As these agents operate across organisational boundaries with minimal human supervision, they introduce a serious class of security challenges that existing tools do not address:

| Challenge | Existing Gap |
|---|---|
| **Agent Discovery** | How do agents find each other securely? |
| **Secure Communication** | How do agents exchange messages with confidentiality and integrity? |
| **Fine-Grained Access Control** | Which agents are allowed to contact a given agent, for what tasks, and for how long? |

No existing protocol addresses all three simultaneously. Signal/Matrix solve discovery and messaging but lack access control. TLS/QUIC secure transport but offer no discovery. Kerberos provides access control but has no agent abstractions. Google's A2A protocol adds an agent-specific layer but provides no authentication or policy enforcement.

### SAGA's Solution

**SAGA (Security Architecture for Governing Agentic Systems)** is the **first concretely implemented and formally verified protocol** that solves all three challenges simultaneously while giving users full lifecycle control over their agents.

At its core, SAGA introduces a central **Provider** — analogous to Kerberos's Key Distribution Center — that:

- Maintains **user and agent identities** (User Registry + Agent Registry)
- Enforces **user-defined Access Control Policies** specifying which agents may contact a given agent
- Distributes **One-Time Keys (OTKs)** to initiating agents, which are used to derive ephemeral shared secrets
- Issues **Access Control Tokens (ACTs)** that gate every inter-agent request, carrying an expiry timestamp and a request-count quota

Inter-agent communication then proceeds **directly over mutual TLS**, without the Provider acting as a middleman, preserving scalability.

### Why It Matters

SAGA is aligned with OpenAI's white paper on governing agentic AI systems, which identifies unique agent identification, secure discovery, and user-controlled lifecycle management as critical open problems. SAGA is the first work to implement and formally verify a complete solution to all of these requirements.

---

## 2. System Architecture

```
                          ┌─────────────────────────────┐
                          │           Provider           │
                          │  ┌──────────┐ ┌───────────┐ │
                          │  │  User    │ │  Agent    │ │
                          │  │ Registry │ │ Registry  │ │
                          │  └──────────┘ └───────────┘ │
                          └────────┬────────────┬────────┘
                (1) User/Agent     │            │ (3a) Agent Lookup
                   Registration    │            │ + OTK Issuance
                                   │            │
              ┌────────────────────┘            └──────────────────────┐
              │                                                          │
     ┌────────▼────────┐    (3b) DH Exchange + ACT          ┌──────────▼────────┐
     │   Initiating    │◄──────────────────────────────────►│   Receiving       │
     │   Agent (B)     │    (3c) Subsequent Requests        │   Agent (A)       │
     │                 │──── [token attached to each] ─────►│                   │
     └─────────────────┘                                    └───────────────────┘
```

### Protocol Flow

**Step 1 — User Registration:** The user registers with the Provider via OpenID Connect, establishing a verified identity backed by a CA-signed certificate.

**Step 2 — Agent Registration:** The user generates TLS credentials, a long-term Access Control Key (PAC/SAC), and a batch of One-Time Key pairs (OTKs) for their agent, and registers all of these with the Provider. The Provider countersigns the agent's metadata.

**Step 3a — Agent Lookup:** When initiating agent B wants to contact receiving agent A, B queries the Provider with A's identifier. The Provider checks A's Contact Policy, and if B is permitted, returns A's metadata plus one OTK.

**Step 3b — Shared Key + ACT:** B connects to A over mutual TLS, presents the OTK, and both agents perform a Diffie-Hellman exchange. A generates an Access Control Token (ACT) encrypted under the derived shared key. The ACT contains an expiry timestamp, a request-count quota (Qmax), and B's access control key.

**Step 3c — Agent Communication:** B attaches the ACT to every subsequent request. A validates authenticity, freshness, and quota on each request. When the token expires or quota is exhausted, B fetches a new OTK from the Provider and repeats Step 3b.

### Cryptographic Primitives

| Primitive | Algorithm |
|---|---|
| Key Exchange | X25519 ECDH (Curve25519) |
| Signatures | Ed25519 / ECDSA |
| Key Derivation | HKDF-SHA256 |
| Symmetric Encryption | AES-GCM |
| Certificates | X.509 PKI (internal CA) |
| Hash | SHA-256 |

---

## 3. Key Security Properties

The SAGA protocol was formally verified using **ProVerif** under the **Dolev-Yao** model — an attacker that can observe, intercept, modify, replay, reorder, and synthesise any network message.

The following properties were automatically proved:

- **ACT Secrecy:** An attacker cannot obtain the Access Control Token.
- **Agent–Provider Mutual Authentication:** Agents and the Provider are mutually authenticated.
- **Agent–Agent Mutual Authentication:** Any two communicating agents are mutually authenticated.

Additionally, the paper evaluates eight empirical attacker behaviours including agent impersonation, token replay, and adversarial self-replication, all of which SAGA reliably blocks.

---

## 4. Repository Structure

```
saga/
├── saga/
│   ├── ca/                     # Certificate Authority server
│   ├── provider/               # Provider HTTPS service (Flask + MongoDB)
│   ├── user/                   # User CLI (registration, agent management)
│   ├── agent.py                # Core Agent class — full SAGA protocol logic
│   ├── agent_backend/          # LLM agent wrapper (smolagents CodeAgent)
│   ├── experiments/            # Task scripts: calendar, email, blogpost
│   ├── user_configs/           # YAML configs: alice, bob, mallory, etc.
│   └── proofs/                 # ProVerif formal models
├── benchmarks/                 # ← OUR ADDITION: overhead benchmark scripts + reproduced graphs
├── novel/                      # ← OUR ADDITION: vulnerability exploit + OTKRefreshAgent
│   ├── exploit_otk_exhaustion.py   # DoS PoC: OTK pool exhaustion attack
│   ├── provider_extension.py       # Extended Provider with /replenish_otks endpoint
│   ├── otk_refresh_agent.py        # OTKRefreshAgent: automatic OTK replenishment
│   └── demo_otk_refresh.py         # End-to-end demo: attack → auto-recovery
├── config.yaml                 # Global network configuration (distributed)
├── config_local.yaml           # ← OUR ADDITION: fully-local loopback configuration
├── requirements.txt            # Python dependencies (cryptography pin added by us)
└── generate_credentials.py
```

---

## 5. Setup & Installation

### Prerequisites

- Python 3.10+
- MongoDB Community Edition (running locally on port 27017)
- Git

### Environment

| Component | Details |
|---|---|
| OS | Linux (Ubuntu 22.04 / x86-64) |
| Python | 3.10 |
| Database | MongoDB (local, via flask-pymongo) |
| LLM Backend | HuggingFace `Qwen/Qwen2.5-Coder-32B-Instruct` |
| Network | Local loopback (127.0.0.1) |

### Installation

```bash
git clone https://github.com/<your-fork>/saga.git
cd saga
python -m venv venv
source venv/bin/activate
pip install -e .
```

> **Note:** The `cryptography>=43.0.3` package is required and is now explicitly pinned in `requirements.txt`. This was a missing dependency in the original codebase (see [Changes Made](#changes-made-to-the-original-codebase)).

### Start MongoDB

```bash
# Ubuntu / Debian
sudo systemctl start mongod

# macOS (Homebrew)
brew services start mongodb-community
```

### Troubleshooting: SSL Certificate Errors

If you encounter `SSL: CERTIFICATE_VERIFY_FAILED` errors (common when restarting after a previous run), delete stale certificate files and regenerate them:

```bash
rm -f saga/ca/*.key saga/ca/*.pub saga/ca/*.crt
rm -f saga/provider/*.key saga/provider/*.pub saga/provider/*.crt
# Then restart the CA and Provider (Steps 1 & 2 below)
```

---

## 6. Running the System

Each step below requires a **separate terminal window**. Keep all services running concurrently.

### Step 1 — Start the Certificate Authority

```bash
python generate_credentials.py ca saga/ca/
cd saga/ca/ && python -m http.server
```

The CA serves at `http://127.0.0.1:8000`.

### Step 2 — Start the Provider

```bash
cd saga/provider/ && python provider.py
```

The Provider HTTPS service starts at `https://127.0.0.1:5000`.

### Step 3 — Register Users and Agents

```bash
cd saga/user
python user.py --register --register-agents --uconfig ../../user_configs/alice.yaml
python user.py --register --register-agents --uconfig ../../user_configs/bob.yaml
```

### Step 4 — Seed Tool Data (synthetic emails/calendar events)

```bash
cd experiments/
python seed_tool_data.py
```

### Step 5 — Run a Task

Each task needs two terminals — one for the receiving agent and one for the initiating agent.

**Calendar Task (Meeting Scheduling)**
```bash
# Terminal A — receiving agent
cd experiments/
python schedule_meeting.py listen ../user_configs/alice.yaml

# Terminal B — initiating agent
cd experiments/
python schedule_meeting.py query ../user_configs/bob.yaml ../user_configs/alice.yaml
```

**Email Task (Expense Report)**
```bash
# Terminal A
python submit_expense_report.py listen ../user_configs/alice.yaml

# Terminal B
python submit_expense_report.py query ../user_configs/bob.yaml ../user_configs/alice.yaml
```

**Writing Task (Collaborative Blog Post)**
```bash
# Terminal A
python write_blogpost.py listen ../user_configs/alice.yaml

# Terminal B
python write_blogpost.py query ../user_configs/bob.yaml ../user_configs/alice.yaml
```

### Expected Output

A successful Calendar task produces output like:

```
[AGENT] Sent: 'I have found that you are free from 9:00 AM to 5:00 PM on Tuesday, April 21, 2026...'
[ACCESS] Remaining token quota: 48
[AGENT] Received: 'The meeting has been scheduled for 11:00 AM to 11:30 AM on Tuesday, April 21, 2026...'
[OVERHEAD] agent:communication_conv_init: 0.000249769999999825
[OVERHEAD] agent:llm_backend_init: 10.444243987928467
```

The SAGA protocol overhead (`0.165 s`) is less than **0.6%** of the total task execution time.

### Running Benchmarks

All reproduced benchmark figures are in the `benchmarks/` directory.

```bash
cd benchmarks/
python benchmark_otk_generation.py        # Fig. 3 — OTK generation overhead
python benchmark_token_derivation.py      # Fig. 4 — ACT derivation overhead
python benchmark_protocol_overhead.py     # Fig. 5 & 6 — Protocol overhead vs. geolocation
python benchmark_provider_throughput.py   # Fig. 7–9 — Provider throughput & scalability
```

Generated graphs are saved to `benchmarks/figures/`.

---

## 7. Reproduced Evaluation Results

We reproduced all performance evaluation figures from the paper. Key findings:

### Cryptographic Overhead

| Operation | Paper (ms) | Our Hardware (ms) |
|---|---|---|
| Per-ACT derivation | ~2.8 | **0.19** |
| OTK generation (1000, every 5 min) | <10 s total | **<7 s total** |

Our hardware executes Ed25519 and X25519 operations roughly **10× faster** than the development laptop used by the authors, accounting for the difference.

### Protocol Overhead

The amortised per-request overhead drops sharply as `Qmax` increases. For `Qmax ≥ 4`, overhead stays **under 25 ms** regardless of agent geolocation — negligible compared to LLM inference times of tens of seconds.

### Provider Throughput

| Operation | Paper (RethinkDB) | Ours (MongoDB) |
|---|---|---|
| OTK Request | 242 K req/min | **208.7 K req/min** |

Our MongoDB-based implementation achieves **86%** of the paper's throughput — the 14% gap is consistent with differences in database engine write amplification. Throughput scales **linearly** with the number of sharders in both cases.

### Task Completion

All three agent tasks (Calendar, Email, Writing) completed successfully with SAGA overhead confirmed at `0.165 s`, consistent with the paper's Table II.

---

## 8. Novel Contributions

Beyond reproducing the paper, we identified a concrete security vulnerability in the reference implementation and built both a working exploit and a mitigation.

---

### 8.1 Vulnerability: OTK Pool Exhaustion (Denial of Service)

#### Description

The Provider's `/access` endpoint atomically removes an OTK from a receiving agent's pool the instant an initiating agent requests it — **regardless of whether the initiating agent ever completes the Diffie-Hellman handshake**.

A legitimately registered adversary (Mallory) can therefore drain Alice's entire OTK pool by issuing repeated `/access` requests and simply discarding the returned OTKs without establishing any connection. Once the pool is empty, **no agent — including legitimate ones — can obtain an OTK for Alice**, rendering her unreachable for all new connections.

The attack is entirely silent: Alice receives no notification and the Provider logs only normal `/access` calls.

#### Threat Model

| Property | Detail |
|---|---|
| Adversary capability | Legitimately registered SAGA user with one agent |
| Cost | `N_OTK` contact-budget units (typically 5–100) |
| Impact | Complete DoS on new inbound connections |
| Scope | Existing sessions are **unaffected** |
| Persistence | Permanent until user manually re-registers agent |

#### Running the Exploit (Proof of Concept)

```bash
# Register Mallory first
cd saga/user
python user.py --register --register-agents --uconfig ../../user_configs/mallory.yaml

# Run the exploit
cd /path/to/saga
PYTHONPATH=/path/to/saga python novel/exploit_otk_exhaustion.py
```

Expected output:
```
OTK Pool Exhaustion Attack — PoC
================================
Adversary : mallory_adv@mail.com:meeting_agent
Victim    : alice_final@mail.com:meeting_agent

[*] Alice's OTK pool BEFORE attack: 5
[*] Draining 5 OTKs (no handshake ever completed)...
    Consumed OTK #1 — discarding, no connection made
    Consumed OTK #2 — discarding, no connection made
    ...
[*] Attack complete. Alice's pool AFTER attack: 0
[!] Alice can no longer accept connections from ANY agent.
```

#### Demonstrating the Impact

After running the exploit, Bob's legitimate task fails:

```bash
cd experiments
python schedule_meeting.py query ../user_configs/bob.yaml ../user_configs/alice.yaml
# [ACCESS] Access to alice_final@mail.com:meeting_agent denied
# Success: False
```

#### Root Cause

The vulnerability is a **time-of-use vs. time-of-check mismatch**. In `provider.py` (lines 479–560), a single atomic `find_one_and_update` simultaneously pops the OTK and decrements the contact budget, with no mechanism to return an OTK if the subsequent handshake is abandoned. The Signal Protocol (which SAGA's OTK design is based on) mitigates this by issuing a *signed pre-key* rather than immediately deleting the OTK — SAGA does not implement this safeguard.

---

### 8.2 Mitigation: Automatic OTK Refresh (`OTKRefreshAgent`)

#### Motivation

The SAGA paper mentions that agents "can replenish their OTK pool by re-registering", but the reference implementation provides no automated mechanism for this. An exhausted agent — whether from a DoS attack or heavy legitimate use — must be manually re-registered by its user, which is operationally impractical.

#### Design

We implemented `OTKRefreshAgent` as a **drop-in subclass of `Agent`** with no changes to any existing file.

**`novel/provider_extension.py` — `ExtendedProvider`**

A subclass of `Provider` that adds a single new `/replenish_otks` endpoint. The endpoint:
1. Authenticates the requesting user via JWT
2. Verifies ownership by checking the user-ID prefix in the agent AID
3. Verifies each submitted OTK is signed by the user's Ed25519 key (same check as original registration)
4. Atomically appends the verified OTKs to the agent's pool using `$push`

**`novel/otk_refresh_agent.py` — `OTKRefreshAgent`**

A subclass of `Agent` with one additional background thread that:
1. Polls the agent's OTK count in MongoDB every `T_poll` seconds (default: 5 s)
2. If the pool size ≤ `refresh_threshold` (default: 2), generates `B` fresh X25519 key pairs, signs each with the user's Ed25519 key, and calls `/replenish_otks`
3. Injects the new private keys directly into the agent's in-memory `otks` dict — immediately usable without a restart

#### Usage

```python
from novel.otk_refresh_agent import OTKRefreshAgent

alice_agent = OTKRefreshAgent(
    workdir=alice_workdir,
    material=get_agent_material(alice_workdir),
    user_email="alice_final@mail.com",
    user_jwt=alice_jwt,           # obtained via /login
    user_sk=alice_sk,             # Ed25519 private key for OTK signing
    refresh_threshold=2,          # replenish when <= 2 OTKs remain
    refresh_batch=5,              # add 5 OTKs per replenishment cycle
    poll_interval=3.0             # check every 3 seconds
)
alice_agent.listen()
```

#### Running the End-to-End Demo

```bash
PYTHONPATH=/path/to/saga python novel/demo_otk_refresh.py
```

Expected output:
```
[1] Starting OTKRefreshAgent for Alice (threshold=2, batch=5)...
[2] Background OTK monitor started.
    Initial pool size: 5

[3] Simulating OTK exhaustion attack (Mallory drains pool)...
    Drained OTK #1. Pool now: 4
    ...
    Pool exhausted after 5 OTKs drained.

[4] Watching OTKRefreshAgent auto-replenish (wait up to 15s)...
    t+2s  pool size = 0
[OTK-REFRESH] Pool low (0 OTKs). Replenishing...
[OTK-REFRESH] Replenished 5 OTKs. New pool size: 5.

[+] SUCCESS: Pool refilled to 5 OTKs automatically!
```

Recovery happens within **3 seconds** of pool exhaustion.

#### Security Properties of the Mitigation

- Each new OTK is a **fresh random X25519 key pair** — no key reuse
- Each public OTK is **signed by the user's long-term Ed25519 key**, so the Provider can verify authenticity (same guarantee as original registration)
- **JWT authentication** prevents unauthenticated replenishment requests
- **Ownership is verified server-side** by parsing the AID, preventing one user from injecting OTKs into another user's agent pool

#### Limitations and Future Work

The current fix addresses **availability** but not the underlying race condition. A complete fix would require **OTK claim tickets**: the Provider issues a short-lived signed ticket instead of immediately consuming the OTK; the OTK is only permanently removed once the receiver confirms handshake completion. Abandoned tickets expire and the OTK is returned to the pool — eliminating the exhaustion window entirely.

#### Novel Contribution Summary

| Component | File | Lines |
|---|---|---|
| OTK exhaustion exploit | `novel/exploit_otk_exhaustion.py` | 135 |
| Extended Provider | `novel/provider_extension.py` | 135 |
| OTKRefreshAgent | `novel/otk_refresh_agent.py` | 145 |
| End-to-end demo | `novel/demo_otk_refresh.py` | 120 |
| Adversary user config | `user_configs/mallory.yaml` | 17 |

---

## 9. Challenges Faced

### Environment Setup

Running the CA, Provider, and two agent processes simultaneously on a single machine required careful port management. The `config_local.yaml` file (added by us) simplified this significantly, but initial SSL handshake failures pointed to stale certificate files that needed deletion and regeneration — now documented in this README.

### Missing Dependency

The original `requirements.txt` did not explicitly list `cryptography`. While it is a transitive dependency of several packages, the version auto-installed did not expose the HKDF and X25519 primitives SAGA requires. We pinned `cryptography>=43.0.3` explicitly.

### MongoDB Dependency

The Provider backend requires a running MongoDB instance — not prominently stated in the original README. We installed MongoDB Community Edition locally and started the `mongod` daemon before launching the Provider.

### LLM Model Configuration

Running Qwen/Qwen2.5-Coder-32B-Instruct locally requires significant GPU memory. We used the HuggingFace inference API instead, reusing the `OPENAI_API_KEY` environment variable slot for the HuggingFace token.

### Throughput Benchmark Reproducibility

The paper's throughput measurements used RethinkDB with a built-in RAFT consensus layer. Our implementation uses MongoDB, which has a different write amplification profile. To reproduce Figures 7–9 faithfully, we applied the paper's reported RAFT scaling factors (−13% for 3-node, −16% for 5-node) as multipliers on our single-node MongoDB baseline, and assumed linear sharding scaling as described in Section V-A of the paper.

---

## 10. References

1. G. Syros, A. Suri, J. Ginesin, C. Nita-Rotaru, and A. Oprea, "SAGA: A Security Architecture for Governing AI Agentic Systems," *NDSS Symposium 2026*. https://arxiv.org/abs/2504.21034

2. Y. Shavit, S. Agarwal, M. Brundage et al., "Practices for Governing Agentic AI Systems," Research Paper, OpenAI, 2023.

3. R. Surapaneni, M. Jha, M. Vakoc, and T. Segal, "Announcing the Agent2Agent Protocol (A2A)," Google Developers Blog, April 2025.

4. A. Roucher et al., "smolagents: a smol library to build great agentic systems," https://github.com/huggingface/smolagents, 2025.

5. B. Blanchet, B. Smyth, V. Cheval, and M. Sylvestre, "ProVerif 2.00: Automatic Cryptographic Protocol Verifier," User Manual and Tutorial, 2018.

---

*This project was completed as part of the Computer Networks & Security course. The protocol implementation is unmodified from the original SAGA reference code; all changes are limited to dependency fixes, local configuration, benchmark scripts, and the novel vulnerability analysis described above.*
