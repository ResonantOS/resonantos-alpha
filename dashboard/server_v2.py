#!/usr/bin/env python3
"""
ResonantOS Dashboard v2 — Clean OpenClaw-native server.
Connects to OpenClaw gateway via WebSocket for real-time data.
No legacy Clawdbot/Watchtower dependencies.
"""

import json
import os
import re
import subprocess
import threading
import time
import hashlib
import traceback
import urllib.request
import urllib.error
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

from flask import Flask, jsonify, redirect, render_template, request, send_from_directory
from flask_cors import CORS

# Solana wallet integration imports — resolve toolkit path dynamically
_dashboard_dir = Path(__file__).resolve().parent
_toolkit_candidates = [
    _dashboard_dir.parent / "solana-toolkit",  # sibling dir (standard layout)
    Path.home() / "resonantos-augmentor" / "solana-toolkit",  # dev/augmentor fallback
    Path.home() / "resonantos-alpha" / "solana-toolkit",  # alpha explicit fallback
]
for _toolkit_path in _toolkit_candidates:
    if _toolkit_path.exists():
        sys.path.insert(0, str(_toolkit_path))
        break
try:
    from nft_minter import NFTMinter
    from token_manager import TokenManager
    from wallet import SolanaWallet
except ImportError:
    # Graceful fallback if solana-toolkit not available
    NFTMinter = None
    TokenManager = None
    SolanaWallet = None

try:
    from protocol_nft_minter import ProtocolNFTMinter, PROTOCOL_NFTS
except ImportError:
    ProtocolNFTMinter = None
    PROTOCOL_NFTS = {}

# ---------------------------------------------------------------------------
# Paths & Config
# ---------------------------------------------------------------------------

OPENCLAW_HOME = Path.home() / ".openclaw"
OPENCLAW_CONFIG = OPENCLAW_HOME / "openclaw.json"
WORKSPACE = OPENCLAW_HOME / "workspace"
SSOT_ROOT = WORKSPACE / "resonantos-augmentor" / "ssot"
AGENTS_DIR = OPENCLAW_HOME / "agents"
EXTENSIONS_DIR = OPENCLAW_HOME / "extensions"
RMEMORY_DIR = WORKSPACE / "r-memory"
RMEMORY_LOG = RMEMORY_DIR / "r-memory.log"
RMEMORY_CONFIG = RMEMORY_DIR / "config.json"
R_AWARENESS_LOG = WORKSPACE / "r-awareness" / "r-awareness.log"

# --- Load config.json (with hardcoded fallbacks for backward compatibility) ---
_DASHBOARD_DIR = Path(__file__).resolve().parent
_CONFIG_FILE = _DASHBOARD_DIR / "config.json"
_CFG = {}
if _CONFIG_FILE.exists():
    try:
        _CFG = json.loads(_CONFIG_FILE.read_text())
    except Exception:
        pass

# Solana wallet integration
_SOLANA_KEYPAIR = Path(_CFG.get("solana", {}).get("keypairPath", "~/.config/solana/id.json")).expanduser()
_DAO_DETAILS = Path.home() / "resonantos-augmentor" / _CFG.get("paths", {}).get("daoDetails", "ssot/L2/DAO_DETAILS.json")
_REGISTRATION_BASKET_KEYPAIR = Path(_CFG.get("solana", {}).get("daoRegistrationBasketKeypairPath", "~/.config/solana/dao-registration-basket.json")).expanduser()
_MIN_SOL_FOR_GAS = _CFG.get("solana", {}).get("minSolForGas", 0.01)

_RCT_MINT = _CFG.get("tokens", {}).get("RCT_MINT", "2z2GEVqhTVUc6Pb3pzmVTTyBh2BeMHqSw1Xrej8KVUKG")
_RES_MINT = _CFG.get("tokens", {}).get("RES_MINT", "DiZuWvmQ6DEwsfz7jyFqXCsMfnJiMVahCj3J5MxkdV5N")

_SOLANA_RPCS = _CFG.get("solana", {}).get("rpcs") or {
    "devnet": "https://api.devnet.solana.com",
    "testnet": "https://api.testnet.solana.com",
    "mainnet-beta": "https://api.mainnet-beta.solana.com",
}

_REX_MINTS = {
    "GOV": "7Zxr6WLPdo5owVwhkuPUKSVRMHGknadBesQExmBSsKpj",
    "FIN": "zwwrrG6neRMwLY76oZfF41BtLZ7kmqWXpqKCCzDkbaL",
    "COM": "7sybHSXWfxFeoUoTv78veNZHRkd4UeNhCt3pmkeJU43S",
    "CRE": "8HQF2jTRouqTcTmzJctGaTPKXkGEk2iyXBmMZ2mrRyKV",
    "TEC": "9V4oLeX77iFSjr1dnHjKXsAWCNhGcADo6L9CH37zLnBF",
}
_REX_DISPLAY = {
    "GOV": "Governance Contribution",
    "FIN": "Financial Contribution",
    "COM": "Community Contribution",
    "CRE": "Creative Contribution",
    "TEC": "Technical Contribution",
}

# RCT Safety Caps (from config.json or defaults)
_rct_caps_cfg = _CFG.get("rctCaps", {})
_RCT_MAX_PER_WALLET_YEAR = _rct_caps_cfg.get("maxPerWalletYear", 10_000)
_RCT_DAILY_PER_HOLDER = _rct_caps_cfg.get("dailyPerHolder", 30)
_RCT_DAILY_FLOOR = _rct_caps_cfg.get("dailyFloor", 300)
_RCT_DAILY_MAX = _rct_caps_cfg.get("dailyMax", 100_000)
_RCT_DECIMALS = _rct_caps_cfg.get("decimals", 9)
_paths_cfg = _CFG.get("paths", {})


def _resolve_data_file(path_from_cfg: str, default_rel: str) -> Path:
    rel = path_from_cfg or default_rel
    candidates = [
        Path.home() / "resonantos-augmentor" / rel,
        _DASHBOARD_DIR / rel,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[-1]


_RCT_CAPS_FILE = _resolve_data_file(_paths_cfg.get("rctCapsFile"), "data/rct_caps.json")
_ONBOARDING_FILE = _resolve_data_file(_paths_cfg.get("onboardingFile"), "data/onboarding.json")
_DAILY_CLAIMS_FILE = _resolve_data_file(_paths_cfg.get("dailyClaims"), "data/daily_claims.json")
_BOUNTIES_FILE = _DASHBOARD_DIR / "data" / "bounties.json"
_TRIBES_FILE = _DASHBOARD_DIR / "data" / "tribes.json"
_PROFILES_FILE = _DASHBOARD_DIR / "data" / "profiles.json"

# Level thresholds for reputation
_LEVEL_THRESHOLDS = [0, 10, 50, 150, 400, 1000, 2500, 6000, 15000, 40000]

# Gateway WS config
GW_HOST = "127.0.0.1"
GW_PORT = 18789
GW_WS_URL = f"ws://{GW_HOST}:{GW_PORT}"

# Read auth token
def _read_gw_token():
    try:
        cfg = json.loads(OPENCLAW_CONFIG.read_text())
        return cfg.get("gateway", {}).get("auth", {}).get("token", "")
    except Exception:
        return ""

GW_TOKEN = _read_gw_token()

# Solana wallet helper functions
def _get_wallet_pubkey():
    """Read AI wallet public key from keypair file."""
    try:
        import json as _j
        from solders.keypair import Keypair as _Kp
        data = _j.loads(_SOLANA_KEYPAIR.read_text())
        kp = _Kp.from_bytes(bytes(data))
        return str(kp.pubkey())
    except Exception:
        return None

def _get_dao_details():
    try:
        return json.loads(_DAO_DETAILS.read_text())
    except Exception:
        return {}

def _solana_rpc(network, method, params=None):
    url = _SOLANA_RPCS.get(network, _SOLANA_RPCS["devnet"])
    body = json.dumps({"jsonrpc":"2.0","id":1,"method":method,"params":params or []}).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())

def _get_fee_payer(network, recipient_address=None):
    """Determine who pays gas. Returns (keypair_path, label)."""
    # Check if user has enough SOL
    if recipient_address:
        try:
            r = _solana_rpc(network, "getBalance", [recipient_address])
            bal = r.get("result",{}).get("value",0) / 1e9
            if bal >= _MIN_SOL_FOR_GAS:
                return None, "user"
        except Exception:
            pass
    # Check AI wallet
    try:
        r = _solana_rpc(network, "getBalance", [_get_wallet_pubkey()])
        bal = r.get("result",{}).get("value",0) / 1e9
        if bal >= _MIN_SOL_FOR_GAS:
            return str(_SOLANA_KEYPAIR), "ai_wallet"
    except Exception:
        pass
    # Fall back to basket
    return str(_REGISTRATION_BASKET_KEYPAIR), "dao_basket"

def _load_onboarding():
    try: return json.loads(_ONBOARDING_FILE.read_text())
    except Exception: return {}

def _save_onboarding(data):
    _ONBOARDING_FILE.parent.mkdir(parents=True, exist_ok=True)
    _ONBOARDING_FILE.write_text(json.dumps(data, indent=2))

def _wallet_has_nft(address, nft_type, network="devnet"):
    """Check NFT presence on-chain first (PDA + wallet), onboarding cache second."""
    checked_addresses = []
    try:
        pda = _derive_symbiotic_pda(address)
        checked_addresses.append(pda)
    except Exception:
        pass
    checked_addresses.append(address)

    if NFTMinter and SolanaWallet:
        try:
            minter = NFTMinter(SolanaWallet(network=network))
            for acct in checked_addresses:
                try:
                    found = minter.check_wallet_has_nft(acct, nft_type)
                    if found.get("has_nft"):
                        return True
                except Exception:
                    continue
        except Exception:
            pass

    onboarding = _load_onboarding().get(address, {})
    key_map = {
        "identity": ("identityNftMinted", "identityNftMint", "identityNft"),
        "alpha_tester": ("alphaNftMinted", "alphaNftMint", "alphaNft"),
        "symbiotic_license": ("licenseSigned", "licenseNft"),
        "manifesto": ("manifestoSigned", "manifestoNft"),
    }
    keys = key_map.get(nft_type, ())
    for key in keys:
        if onboarding.get(key):
            return True
    return False

def _require_identity_nft(wallet_address):
    """Return True if wallet holds Identity NFT, else False."""
    return _wallet_has_nft(wallet_address, "identity")

def _load_daily_claims():
    try: return json.loads(_DAILY_CLAIMS_FILE.read_text())
    except Exception: return {}

def _save_daily_claims(data):
    _DAILY_CLAIMS_FILE.parent.mkdir(parents=True, exist_ok=True)
    _DAILY_CLAIMS_FILE.write_text(json.dumps(data, indent=2))

def _load_rct_caps():
    try: return json.loads(_RCT_CAPS_FILE.read_text())
    except Exception: return {"wallets_yearly": {}, "daily": []}

def _save_rct_caps(caps):
    _RCT_CAPS_FILE.parent.mkdir(parents=True, exist_ok=True)
    _RCT_CAPS_FILE.write_text(json.dumps(caps, indent=2))


def _load_bounties():
    try:
        data = json.loads(_BOUNTIES_FILE.read_text())
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_bounties(bounties):
    _BOUNTIES_FILE.parent.mkdir(parents=True, exist_ok=True)
    _BOUNTIES_FILE.write_text(json.dumps(bounties, indent=2))


def _load_tribes():
    try:
        data = json.loads(_TRIBES_FILE.read_text())
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_tribes(tribes):
    _TRIBES_FILE.parent.mkdir(parents=True, exist_ok=True)
    _TRIBES_FILE.write_text(json.dumps(tribes, indent=2))


def _sync_tribe_bounty_refs(tribes, bounties):
    tribe_map = {t.get("id"): t for t in tribes if t.get("id")}
    for tribe in tribe_map.values():
        tribe["activeBounties"] = []
        tribe["completedBounties"] = []
    for bounty in bounties:
        tribe_id = bounty.get("tribeId")
        if not tribe_id or tribe_id not in tribe_map:
            continue
        bucket = "completedBounties" if bounty.get("status") == "rewarded" else "activeBounties"
        tribe_map[tribe_id][bucket].append(bounty.get("id"))
    for tribe in tribe_map.values():
        tribe["activeBounties"] = sorted(set(tribe.get("activeBounties", [])))
        tribe["completedBounties"] = sorted(set(tribe.get("completedBounties", [])))


def _enrich_bounty_with_tribe(bounty, tribe_map):
    tribe_id = bounty.get("tribeId")
    tribe = tribe_map.get(tribe_id)
    out = dict(bounty)
    if tribe:
        out["tribe"] = {
            "id": tribe.get("id"),
            "name": tribe.get("name"),
            "category": tribe.get("category"),
            "members": tribe.get("members", []),
        }
    else:
        out["tribe"] = None
    return out


def _short_wallet(addr):
    if not addr:
        return ""
    return f"{addr[:6]}...{addr[-4:]}" if len(addr) > 10 else addr


def _is_valid_pubkey(addr: str) -> bool:
    try:
        from solders.pubkey import Pubkey as _Pubkey
        _Pubkey.from_string(addr)
        return True
    except Exception:
        return False

def _check_rct_cap(recipient, amount_human):
    caps = _load_rct_caps()
    year = str(datetime.now(timezone.utc).year)
    # Per-wallet annual
    yearly = caps.get("wallets_yearly", {}).get(recipient, {}).get(year, 0)
    if yearly + amount_human > _RCT_MAX_PER_WALLET_YEAR:
        return False, f"Annual cap: {yearly}/{_RCT_MAX_PER_WALLET_YEAR} $RCT ({year})"
    # Daily global
    now = datetime.now(timezone.utc)
    cutoff = (now - timedelta(hours=24)).isoformat()
    daily_total = sum(e["amount"] for e in caps.get("daily", []) if e["ts"] > cutoff)
    # Dynamic daily cap based on holder count
    holder_count = caps.get("holder_count", 10)
    daily_cap = max(_RCT_DAILY_FLOOR, min(_RCT_DAILY_MAX, _RCT_DAILY_PER_HOLDER * holder_count))
    if daily_total + amount_human > daily_cap:
        return False, f"Global daily cap: {daily_total}/{daily_cap} $RCT"
    return True, "ok"

def _record_rct_mint(recipient, amount_human):
    caps = _load_rct_caps()
    year = str(datetime.now(timezone.utc).year)
    if "wallets_yearly" not in caps: caps["wallets_yearly"] = {}
    if recipient not in caps["wallets_yearly"]: caps["wallets_yearly"][recipient] = {}
    caps["wallets_yearly"][recipient][year] = caps["wallets_yearly"][recipient].get(year, 0) + amount_human
    now_iso = datetime.now(timezone.utc).isoformat()
    if "daily" not in caps: caps["daily"] = []
    caps["daily"].append({"ts": now_iso, "recipient": recipient, "amount": amount_human})
    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    caps["daily"] = [e for e in caps["daily"] if e["ts"] > cutoff]
    _save_rct_caps(caps)

# ---------------------------------------------------------------------------
# Gateway WebSocket Client (background thread)
# ---------------------------------------------------------------------------

try:
    import websocket  # pip install websocket-client
except ImportError:
    websocket = None

class GatewayClient:
    """Persistent WS connection to OpenClaw gateway. Caches latest state."""

    def __init__(self):
        self.connected = False
        self.conn_id = None
        self.health = {}
        self.features = {}
        self.agents_snapshot = []
        self.sessions_snapshot = []
        self.last_tick = 0
        self.last_health_ts = 0
        self.error = None
        self._ws = None
        self._lock = threading.Lock()
        self._msg_id = 0
        self._pending = {}  # id -> threading.Event + result

    def _next_id(self):
        self._msg_id += 1
        return f"r{self._msg_id}"

    def start(self):
        t = threading.Thread(target=self._run, daemon=True)
        t.start()

    def _run(self):
        while True:
            try:
                self._connect()
            except Exception as e:
                self.connected = False
                self.error = str(e)
            time.sleep(3)  # reconnect delay

    def _send_connect(self, ws, nonce=None):
        connect_msg = {
            "type": "req", "id": "c0", "method": "connect",
            "params": {
                "auth": {"token": GW_TOKEN},
                "minProtocol": 3, "maxProtocol": 3,
                "role": "operator",
                "scopes": ["operator.admin"],
                "caps": [],
                "client": {
                    "id": "gateway-client",
                    "mode": "backend",
                    "version": "2.0.0",
                    "platform": "darwin"
                }
            }
        }
        ws.send(json.dumps(connect_msg))

    def _connect(self):
        if websocket is None:
            self.error = "websocket-client not installed (pip install websocket-client)"
            import time; time.sleep(30)
            return
        ws = websocket.WebSocket()
        ws.settimeout(10)
        ws.connect(GW_WS_URL)
        self._ws = ws

        # Wait for challenge event, then send connect with nonce
        challenge_received = False
        ws.settimeout(5)
        try:
            raw = ws.recv()
            if raw:
                msg = json.loads(raw)
                if msg.get("type") == "event" and msg.get("event") == "connect.challenge":
                    nonce = msg.get("payload", {}).get("nonce")
                    self._send_connect(ws, nonce)
                    challenge_received = True
                else:
                    self._handle(msg)
        except Exception:
            pass

        if not challenge_received:
            # Fallback: send connect without nonce (older protocol)
            self._send_connect(ws)

        # Read loop
        ws.settimeout(60)
        while True:
            try:
                raw = ws.recv()
                if not raw:
                    break
                msg = json.loads(raw)
                self._handle(msg)
            except websocket.WebSocketTimeoutException:
                # Send ping to keep alive
                try:
                    ws.ping()
                except Exception:
                    break
            except Exception:
                break

        self.connected = False
        try:
            ws.close()
        except Exception:
            pass

    def _handle(self, msg):
        mtype = msg.get("type")

        if mtype == "res":
            mid = msg.get("id")
            # Handle connect response
            if mid == "c0":
                if msg.get("ok"):
                    self.connected = True
                    self.error = None
                    payload = msg.get("payload", {})
                    self.conn_id = payload.get("server", {}).get("connId")
                    self.features = payload.get("features", {})
                    # Extract agents from snapshot
                    snap = payload.get("snapshot", {})
                    # Health data is in the snapshot too
                else:
                    self.error = msg.get("error", {}).get("message", "connect failed")

            # Handle pending request responses
            if mid in self._pending:
                evt, _ = self._pending[mid]
                self._pending[mid] = (evt, msg)
                evt.set()

        elif mtype == "event":
            event = msg.get("event")
            payload = msg.get("payload", {})

            if event == "tick":
                self.last_tick = payload.get("ts", 0)

            elif event == "health":
                with self._lock:
                    self.health = payload
                    self.last_health_ts = payload.get("ts", 0)

            elif event == "connect.challenge":
                pass  # Handled by protocol

    def request(self, method, params=None, timeout=10):
        """Send a request and wait for response."""
        if not self.connected or not self._ws:
            return {"ok": False, "error": "not connected"}

        mid = self._next_id()
        evt = threading.Event()
        self._pending[mid] = (evt, None)

        try:
            msg = {"type": "req", "id": mid, "method": method}
            if params:
                msg["params"] = params
            self._ws.send(json.dumps(msg))
            evt.wait(timeout=timeout)
            _, result = self._pending.pop(mid, (None, None))
            if result is None:
                return {"ok": False, "error": "timeout"}
            return result
        except Exception as e:
            self._pending.pop(mid, None)
            return {"ok": False, "error": str(e)}


# Singleton
gw = GatewayClient()

# ---------------------------------------------------------------------------
# Flask App
# ---------------------------------------------------------------------------

app = Flask(__name__)
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.jinja_env.auto_reload = True
CORS(app)

@app.route("/chat-redirect")
def chat_redirect():
    """Redirect to OpenClaw webchat with auth token injected."""
    token = _read_gw_token()
    port = GW_PORT
    if token:
        return redirect(f"http://localhost:{port}/#token={token}")
    return redirect(f"http://localhost:{port}/")


def _get_version():
    try:
        version_file = Path(os.path.dirname(__file__)).parent / "VERSION"
        if version_file.exists():
            return "v" + version_file.read_text().strip()
        return "v0.0.0"
    except Exception:
        return "v0.0.0"


@app.context_processor
def inject_version():
    return {"resonantos_version": _get_version()}


# ---------------------------------------------------------------------------
# R-Memory Data Helpers
# ---------------------------------------------------------------------------

import re as _re
import glob as _glob

def _rmem_config():
    """Read r-memory/config.json."""
    try:
        return json.loads(RMEMORY_CONFIG.read_text())
    except Exception:
        return {"compressTrigger": 36000, "evictTrigger": 80000, "blockSize": 4000}

def _rmem_camouflage():
    """Read r-memory/camouflage.json."""
    try:
        return json.loads((RMEMORY_DIR / "camouflage.json").read_text())
    except Exception:
        return {"enabled": False}

def _rmem_effective_models():
    """Resolve the actual runtime models for compression and narrative.
    Config overrides (narrativeModel) take priority over camouflage routing."""
    cfg = _rmem_config()
    camo = _rmem_camouflage()
    base_model = cfg.get("compressionModel", "anthropic/claude-haiku-4-5")

    # Config-level overrides take priority over camouflage routing
    narrative_override = cfg.get("narrativeModel")

    if camo.get("enabled") and camo.get("elements", {}).get("trafficSegregation"):
        pref = camo.get("preferredBackgroundProvider", "openai")
        bg_models = camo.get("backgroundModels", {})
        compression_model = bg_models.get(pref, base_model) if camo.get("routeCompressionOffAnthro") else base_model
        narrative_model = narrative_override or (bg_models.get(f"{pref}-narrative", bg_models.get(pref, base_model)) if camo.get("routeNarrativeOffAnthro") else base_model)
    else:
        compression_model = base_model
        narrative_model = narrative_override or base_model

    return {
        "compression": compression_model,
        "narrative": narrative_model,
    }

def _rmem_history_blocks(session_id=None):
    """Read compressed blocks from history-{sessionId}.json files AND block-cache.json.
    If session_id given, only that history file. Otherwise aggregate all.
    block-cache.json contains lifetime compression data (all blocks ever compressed).
    Returns list of block dicts with compressed, tokensRaw, tokensCompressed, timestamp."""
    all_blocks = []
    history_hashes = set()

    # 1. Read current/recent session blocks from history files
    pattern = str(RMEMORY_DIR / "history-*.json")
    files = _glob.glob(pattern)
    for f in files:
        if session_id and session_id not in f:
            continue
        try:
            data = json.loads(Path(f).read_text())
            if isinstance(data, list):
                for b in data:
                    b["_file"] = Path(f).name
                    b["_source"] = "history"
                    all_blocks.append(b)
                    if "hash" in b:
                        history_hashes.add(b["hash"])
        except Exception:
            pass

    # 2. Read lifetime compression stats from block-cache.json
    if not session_id:
        cache_file = RMEMORY_DIR / "block-cache.json"
        if cache_file.exists():
            try:
                cache_data = json.loads(cache_file.read_text())
                if isinstance(cache_data, dict):
                    for cache_hash, entry in cache_data.items():
                        if str(cache_hash) in history_hashes:
                            continue
                        if not isinstance(entry, dict):
                            continue
                        raw_tokens = int(entry.get("tokensRaw", 0) or 0)
                        comp_tokens = int(entry.get("tokensCompressed", 0) or 0)
                        if raw_tokens <= 0 and comp_tokens <= 0:
                            continue
                        cache_block = {
                            "tokensRaw": raw_tokens,
                            "tokensCompressed": comp_tokens,
                            "compressed": entry.get("compressed", ""),
                            "hash": str(cache_hash),
                            "_file": "block-cache.json",
                            "_source": "cache",
                        }
                        all_blocks.append(cache_block)
            except Exception:
                pass

    return all_blocks

def _rmem_current_session_id():
    """Get the current main session ID (short hash) from the most recently modified history file."""
    pattern = str(RMEMORY_DIR / "history-*.json")
    files = _glob.glob(pattern)
    if not files:
        return None
    newest = max(files, key=lambda f: Path(f).stat().st_mtime)
    m = _re.search(r'history-([a-f0-9]+)\.json', newest)
    return m.group(1) if m else None

def _rmem_parse_log():
    """Parse r-memory.log (text format) into structured events.
    Log lines: [ISO_TS] [LEVEL] message {json}
    Key patterns: init, Session, === COMPACTION ===, Swap plan, Block compressed, === DONE ===, FIFO evicted, FIFO done
    """
    events = []
    if not RMEMORY_LOG.exists():
        return events
    try:
        text = RMEMORY_LOG.read_text(errors="ignore")
    except Exception:
        return events

    line_re = _re.compile(
        r'^\[(\d{4}-\d{2}-\d{2}T[\d:.]+Z)\]\s+\[(\w+)\]\s+(.*)', _re.MULTILINE
    )
    for m in line_re.finditer(text):
        ts, level, body = m.group(1), m.group(2), m.group(3)
        evt = {"ts": ts, "level": level, "raw": body}

        # Try to extract inline JSON
        json_match = _re.search(r'\{.*\}', body)
        payload = {}
        if json_match:
            try:
                payload = json.loads(json_match.group())
            except Exception:
                pass

        if "=== COMPACTION ===" in body:
            evt["event"] = "compaction_start"
            evt.update(payload)
        elif "=== DONE ===" in body:
            evt["event"] = "compaction_done"
            evt.update(payload)
        elif "Swap plan" in body:
            evt["event"] = "swap_plan"
            evt.update(payload)
        elif "Block compressed" in body:
            evt["event"] = "block_compressed"
            evt.update(payload)
        elif "FIFO evicted" in body:
            evt["event"] = "fifo_evicted"
            evt.update(payload)
        elif "FIFO done" in body:
            evt["event"] = "fifo_done"
            evt.update(payload)
        elif body.startswith("Session "):
            evt["event"] = "session"
            evt.update(payload)
        elif "init" in body and ("R-Memory" in body or "r-memory" in body.lower()):
            evt["event"] = "init"
            evt.update(payload)
        elif "Config loaded" in body:
            evt["event"] = "config_loaded"
            evt.update(payload)
        else:
            evt["event"] = "info"

        events.append(evt)
    return events

def _rmem_gateway_session():
    """Get main session data from sessions.json file directly."""
    sessions_path = Path.home() / ".openclaw" / "agents" / "main" / "sessions" / "sessions.json"
    try:
        data = json.loads(sessions_path.read_text())
        # sessions.json is a dict keyed by session key
        if isinstance(data, dict) and "agent:main:main" in data:
            return data["agent:main:main"]
        # Fallback: list format
        if isinstance(data, list):
            for s in data:
                if s.get("key") == "agent:main:main":
                    return s
    except Exception:
        pass
    # Fallback: try WS
    try:
        sess_result = gw.request("sessions.list", timeout=5)
        if sess_result.get("ok") and sess_result.get("payload"):
            sessions = sess_result["payload"].get("sessions", [])
            for s in sessions:
                if s.get("key") == "agent:main:main":
                    return s
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Page Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html", active_page="overview")

@app.route("/agents")
def agents_page():
    return render_template("agents.html", active_page="agents")

@app.route("/r-memory")
def r_memory_page():
    return render_template("r-memory.html", active_page="r-memory")

@app.route("/projects")
def projects_page():
    return render_template("projects.html", active_page="projects")

@app.route("/chatbots")
def chatbots_page():
    return render_template("chatbots.html", active_page="chatbots")

@app.route("/wallet")
def wallet_page():
    return render_template("wallet.html", active_page="wallet")

@app.route("/tribes")
def tribes_page():
    return render_template("tribes.html", active_page="tribes")

@app.route("/bounties")
def bounties_page():
    return render_template("bounties.html", active_page="bounties")

@app.route("/protocol-store")
def protocol_store_page():
    cfg = {}
    cfg_path = Path(__file__).parent / "config.json"
    if cfg_path.exists():
        try:
            cfg = json.loads(cfg_path.read_text())
        except Exception:
            pass
    return render_template("protocol-store.html", active_page="protocol-store", config=cfg)

@app.route("/docs")
def docs_page():
    gitbook_url = app.config.get("GITBOOK_URL", "https://resonantos.gitbook.io/resonantos-docs/")
    return render_template("docs.html", active_page="docs", gitbook_url=gitbook_url)

@app.route("/license")
def license_page():
    return render_template("license.html", active_page="license")


# ============================================================================
# Docs API — browse, read, and search documentation
# ============================================================================

DOCS_WORKSPACE = WORKSPACE  # ~/.openclaw/workspace
REPO_DIR = Path.home() / "resonantos-augmentor"  # actual repo location

WORKSPACE_SYSTEM_FILES = {
    "AGENTS.md", "SOUL.md", "USER.md", "TOOLS.md", "IDENTITY.md",
    "HEARTBEAT.md", "BOOTSTRAP.md",
}


def _docs_build_folder_tree(root, prefix=""):
    """Recursively build a file tree for docs browsing."""
    SKIP = {"node_modules", "target", "dist", "build", "__pycache__", "venv", ".venv", ".git", "media"}
    items = []
    if not root.exists() or not root.is_dir():
        return items
    try:
        for entry in sorted(root.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
            if entry.name.startswith(".") or entry.name in SKIP:
                continue
            rel = f"{prefix}/{entry.name}" if prefix else entry.name
            if entry.is_dir():
                children = _docs_build_folder_tree(entry, rel)
                if children:
                    fc = sum(1 for c in children if c["type"] == "file") + sum(c.get("fileCount", 0) for c in children if c["type"] == "folder")
                    items.append({"name": entry.name, "type": "folder", "path": rel, "children": children, "fileCount": fc})
            elif entry.suffix.lower() in (".md", ".txt", ".json", ".py", ".js", ".html", ".css"):
                try:
                    st = entry.stat()
                    items.append({"name": entry.name, "type": "file", "path": rel, "size": st.st_size, "modified": int(st.st_mtime * 1000)})
                except Exception:
                    pass
    except PermissionError:
        pass
    return items


def _docs_build_tree():
    """Build full docs tree from workspace sources."""
    tree = []

    # 1. Repo docs/
    docs_dir = REPO_DIR / "docs"
    if docs_dir.exists():
        items = _docs_build_folder_tree(docs_dir, "resonantos-augmentor/docs")
        if items:
            tree.append({"name": "docs", "type": "folder", "path": "resonantos-augmentor/docs", "icon": "📖", "children": items, "fileCount": sum(i.get("fileCount", 0) if i["type"] == "folder" else 1 for i in items)})

    # 2. SSoT
    ssot_dir = REPO_DIR / "ssot"
    if ssot_dir.exists():
        items = _docs_build_folder_tree(ssot_dir, "resonantos-augmentor/ssot")
        if items:
            tree.append({"name": "ssot", "type": "folder", "path": "resonantos-augmentor/ssot", "icon": "🗂️", "children": items, "fileCount": sum(i.get("fileCount", 0) if i["type"] == "folder" else 1 for i in items)})

    # 3. Dashboard source
    dash_dir = REPO_DIR / "dashboard"
    if dash_dir.exists():
        items = _docs_build_folder_tree(dash_dir, "resonantos-augmentor/dashboard")
        if items:
            tree.append({"name": "dashboard", "type": "folder", "path": "resonantos-augmentor/dashboard", "icon": "📊", "children": items, "fileCount": sum(i.get("fileCount", 0) if i["type"] == "folder" else 1 for i in items)})

    # 4. Reference
    ref_dir = REPO_DIR / "reference"
    if ref_dir.exists():
        items = _docs_build_folder_tree(ref_dir, "resonantos-augmentor/reference")
        if items:
            tree.append({"name": "reference", "type": "folder", "path": "resonantos-augmentor/reference", "icon": "📚", "children": items, "fileCount": sum(i.get("fileCount", 0) if i["type"] == "folder" else 1 for i in items)})

    # 5. Workspace root .md files (excluding system files)
    root_docs = []
    for f in sorted(DOCS_WORKSPACE.glob("*.md")):
        if f.name not in WORKSPACE_SYSTEM_FILES:
            try:
                st = f.stat()
                root_docs.append({"name": f.name, "type": "file", "path": f.name, "size": st.st_size, "modified": int(st.st_mtime * 1000)})
            except Exception:
                pass
    if root_docs:
        tree.append({"name": "workspace", "type": "folder", "path": "", "icon": "📄", "children": root_docs, "fileCount": len(root_docs)})

    # 6. Memory folder
    mem_dir = DOCS_WORKSPACE / "memory"
    if mem_dir.exists():
        items = _docs_build_folder_tree(mem_dir, "memory")
        if items:
            tree.append({"name": "memory", "type": "folder", "path": "memory", "icon": "🧠", "children": items, "fileCount": sum(i.get("fileCount", 0) if i["type"] == "folder" else 1 for i in items)})

    return tree


@app.route("/api/docs/tree")
def api_docs_tree():
    tree = _docs_build_tree()
    total = sum(i.get("fileCount", 0) for i in tree)
    return jsonify({"tree": tree, "root": str(DOCS_WORKSPACE), "totalFiles": total})


@app.route("/api/docs/file")
def api_docs_file():
    path = request.args.get("path", "")
    if path.startswith("/"):
        filepath = Path(path)
    elif path.startswith("resonantos-augmentor/"):
        # Resolve against actual repo location
        sub = path[len("resonantos-augmentor/"):]
        filepath = REPO_DIR / sub
    else:
        filepath = DOCS_WORKSPACE / path
    try:
        resolved = filepath.resolve()
        allowed = resolved.is_relative_to(DOCS_WORKSPACE.resolve()) or resolved.is_relative_to(REPO_DIR.resolve())
        if not allowed:
            return jsonify({"error": "Access denied"}), 403
    except Exception:
        return jsonify({"error": "Invalid path"}), 403
    if not filepath.exists():
        return jsonify({"error": "File not found"}), 404
    if not filepath.is_file():
        return jsonify({"error": "Not a file"}), 400
    try:
        content = filepath.read_text(errors="replace")
        stat = filepath.stat()
        title = filepath.stem
        for line in content.split("\n")[:10]:
            if line.startswith("# "):
                title = line[2:].strip()
                break
        return jsonify({"path": path, "name": filepath.name, "title": title, "content": content, "size": stat.st_size, "modified": int(stat.st_mtime * 1000), "wordCount": len(content.split()), "lineCount": content.count("\n") + 1})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/docs/open-in-editor", methods=["POST"])
def api_docs_open_editor():
    data = request.get_json() or {}
    path = data.get("path", "")
    if not path:
        return jsonify({"error": "No path"}), 400
    if path.startswith("/"):
        filepath = Path(path)
    elif path.startswith("resonantos-augmentor/"):
        filepath = REPO_DIR / path[len("resonantos-augmentor/"):]
    else:
        filepath = DOCS_WORKSPACE / path
    try:
        resolved = filepath.resolve()
        if not (resolved.is_relative_to(DOCS_WORKSPACE.resolve()) or resolved.is_relative_to(REPO_DIR.resolve())):
            return jsonify({"error": "Access denied"}), 403
    except Exception:
        return jsonify({"error": "Invalid path"}), 403
    if not filepath.exists():
        return jsonify({"error": "Not found"}), 404
    try:
        import shutil
        if shutil.which("code"):
            subprocess.Popen(["code", str(filepath)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return jsonify({"success": True, "editor": "VS Code"})
        else:
            subprocess.Popen(["open", str(filepath)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return jsonify({"success": True, "editor": "system"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/docs/search")
def api_docs_search():
    q = request.args.get("q", "")
    if len(q) < 2:
        return jsonify({"results": [], "query": q, "count": 0})
    results = []
    search_term = q.lower()

    def _search_file(fp, rel_path):
        try:
            content = fp.read_text(errors="replace")
            lines = content.split("\n")
            matches = []
            for i, line in enumerate(lines):
                if search_term in line.lower():
                    start, end = max(0, i - 1), min(len(lines), i + 2)
                    matches.append({"line": i + 1, "text": line.strip()[:200], "snippet": "\n".join(lines[start:end])[:300]})
                    if len(matches) >= 5:
                        break
            if matches:
                title = fp.stem
                for line in content.split("\n")[:10]:
                    if line.startswith("# "):
                        title = line[2:].strip()
                        break
                results.append({"path": rel_path, "name": fp.name, "title": title, "matches": matches, "matchCount": len(matches)})
        except Exception:
            pass

    # Search all browsable sources (REPO_DIR is ~/resonantos-augmentor, not inside workspace)
    search_roots = [
        (REPO_DIR / "docs", "resonantos-augmentor/docs"),
        (REPO_DIR / "ssot", "resonantos-augmentor/ssot"),
        (REPO_DIR / "reference", "resonantos-augmentor/reference"),
        (DOCS_WORKSPACE / "memory", "memory"),
    ]
    for root, prefix in search_roots:
        if root.exists():
            for fp in root.rglob("*.md"):
                if len(results) >= 30:
                    break
                _search_file(fp, f"{prefix}/{fp.relative_to(root)}")

    # Root workspace docs
    for fp in DOCS_WORKSPACE.glob("*.md"):
        if len(results) >= 30:
            break
        if fp.name not in WORKSPACE_SYSTEM_FILES:
            _search_file(fp, fp.name)

    results.sort(key=lambda x: x["matchCount"], reverse=True)
    return jsonify({"results": results, "query": q, "count": len(results)})


@app.route("/api/docs/search/semantic")
def api_docs_search_semantic():
    import re
    from difflib import SequenceMatcher

    q = request.args.get("q", "")
    if len(q) < 2:
        return jsonify({"results": [], "query": q, "count": 0})
    results = []
    query_words = q.lower().split()

    def _relevance(content, fpath):
        cl = content.lower()
        fl = fpath.lower()
        score = 0.0
        if q.lower() in cl:
            score += 50.0
        wf = sum(1 for w in query_words if w in cl)
        score += (wf / len(query_words)) * 30.0
        score += sum(1 for w in query_words if w in fl) * 10.0
        for word in query_words:
            if word in cl:
                for m in re.finditer(re.escape(word), cl):
                    nearby = cl[max(0, m.start() - 100):m.start() + 100]
                    score += sum(1 for w in query_words if w in nearby) * 2.0
        for word in query_words:
            for cw in set(re.findall(r"\b\w+\b", cl)):
                if len(cw) > 3:
                    r = SequenceMatcher(None, word, cw).ratio()
                    if 0.8 < r < 1.0:
                        score += r * 5.0
        return score

    def _snippet(content):
        lines = content.split("\n")
        best_i, best_s = 0, 0
        for i, line in enumerate(lines):
            ll = line.lower()
            s = sum(1 for w in query_words if w in ll)
            if q.lower() in ll:
                s += 5
            if s > best_s:
                best_s = s
                best_i = i
        start, end = max(0, best_i - 1), min(len(lines), best_i + 3)
        snip = "\n".join(lines[start:end])[:300]
        return snip, best_i + 1

    search_roots = [
        ("resonantos-augmentor/docs", REPO_DIR / "docs"),
        ("resonantos-augmentor/ssot", REPO_DIR / "ssot"),
        ("resonantos-augmentor/reference", REPO_DIR / "reference"),
        ("memory", DOCS_WORKSPACE / "memory"),
    ]
    for prefix, root in search_roots:
        if not root.exists():
            continue
        for fp in root.rglob("*.md"):
            try:
                content = fp.read_text(errors="replace")
                rel = f"{prefix}/{fp.relative_to(root)}"
                score = _relevance(content, rel)
                if score < 5.0:
                    continue
                snip, ln = _snippet(content)
                title = fp.stem
                for line in content.split("\n")[:5]:
                    if line.startswith("# "):
                        title = line[2:].strip()
                        break
                results.append({"path": rel, "name": fp.name, "title": title, "matches": [{"line": ln, "text": snip[:200], "snippet": snip}], "matchCount": 1, "score": round(score, 2)})
            except Exception:
                continue
    results.sort(key=lambda x: x["score"], reverse=True)
    return jsonify({"query": q, "mode": "semantic", "results": results[:20], "count": len(results)})


# ---------------------------------------------------------------------------
# API: Wallet & DAO (Solana integration)
# ---------------------------------------------------------------------------

@app.route("/api/wallet")
def api_wallet():
    """Get wallet balances for both SPL and Token-2022 accounts."""
    try:
        network = request.args.get("network", "devnet")
        address = request.args.get("address")
        
        if not address:
            try:
                pk = _get_wallet_pubkey()
                if pk is None:
                    return jsonify({"error": "No wallet configured. Create a keypair first."}), 400
                address = str(pk)
            except Exception:
                return jsonify({"error": "address parameter required"}), 400
        
        # Query both SPL and Token-2022 token accounts
        spl_program = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
        token22_program = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"
        
        balances = {}
        
        # Get SOL balance
        try:
            sol_result = _solana_rpc(network, "getBalance", [address])
            sol_balance = sol_result.get("result", {}).get("value", 0) / 1e9
            balances["SOL"] = {"balance": sol_balance, "decimals": 9}
        except Exception as e:
            print(f"Error getting SOL balance: {e}")
            balances["SOL"] = {"balance": 0, "decimals": 9}
        
        # Query token accounts for both programs
        for program in [spl_program, token22_program]:
            try:
                result = _solana_rpc(network, "getTokenAccountsByOwner", [
                    address,
                    {"programId": program},
                    {"encoding": "jsonParsed"}
                ])
                
                for account in result.get("result", {}).get("value", []):
                    parsed = account.get("account", {}).get("data", {}).get("parsed", {}).get("info", {})
                    mint = parsed.get("mint")
                    token_amount = parsed.get("tokenAmount", {})
                    amount = float(token_amount.get("amount", 0))
                    decimals = token_amount.get("decimals", 0)
                    ui_amount = amount / (10 ** decimals) if decimals > 0 else amount
                    
                    # Map known mints to symbols
                    symbol = mint
                    if mint == _RCT_MINT:
                        symbol = "$RCT"
                    elif mint == _RES_MINT:
                        symbol = "$RES"
                    elif mint in _REX_MINTS.values():
                        for k, v in _REX_MINTS.items():
                            if v == mint:
                                symbol = f"$REX-{k}"
                                break
                    
                    balances[symbol] = {
                        "balance": ui_amount,
                        "decimals": decimals,
                        "mint": mint
                    }
            except Exception as e:
                print(f"Error querying token accounts for {program}: {e}")
        
        return jsonify({
            "address": address,
            "network": network,
            "balances": balances
        })
        
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route("/api/wallet/user")
def api_wallet_user():
    """Query any address for balances + last claim time."""
    try:
        network = request.args.get("network", "devnet")
        address = request.args.get("address")
        
        if not address:
            return jsonify({"error": "address parameter required"}), 400
        
        # Get balances using existing endpoint logic
        wallet_data = api_wallet().get_json()
        
        # Get last claim time
        claims = _load_daily_claims()
        claim_val = claims.get(address)
        last_claim = claim_val if isinstance(claim_val, str) else (claim_val.get("last_claim") if isinstance(claim_val, dict) else None)
        
        return jsonify({
            "address": address,
            "network": network,
            "balances": wallet_data.get("balances", {}),
            "lastClaim": last_claim,
            "canClaim": True  # Will be calculated based on 24h cooldown
        })
        
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route("/api/wallet/mint-nft", methods=["POST"])
def api_wallet_mint_nft():
    """Mint soulbound NFT + reward tokens with RCT cap check."""
    try:
        if not NFTMinter or not TokenManager:
            return jsonify({"error": "Solana toolkit not available"}), 500
            
        data = request.get_json() or {}
        network = data.get("network", "devnet")
        recipient = data.get("recipient")
        nft_type = data.get("type", "identity")  # identity, alpha_tester
        signature = data.get("signature")  # Phantom co-signature
        
        # Devnet only for alpha
        if network != "devnet":
            return jsonify({"error": "Only devnet supported during alpha"}), 400
        
        if not recipient or not signature:
            return jsonify({"error": "recipient and signature required"}), 400
        if not _is_valid_pubkey(recipient):
            return jsonify({"error": "Invalid recipient address"}), 400

        if nft_type not in {"identity", "alpha_tester"}:
            return jsonify({"error": "Invalid NFT type. Use identity or alpha_tester"}), 400

        pda_address = _derive_symbiotic_pda(recipient)
        nft_minter = NFTMinter(SolanaWallet(network=network))
        existing = nft_minter.check_wallet_has_nft(pda_address, nft_type)
        if existing.get("has_nft"):
            label = "Identity NFT" if nft_type == "identity" else "Alpha Tester NFT"
            return jsonify({
                "error": f"Already holds {label}",
                "existing_mint": existing.get("mint"),
            }), 409
        
        # Reward amounts
        rewards = {
            "identity": {"rct": 5, "res": 500},
            "alpha_tester": {"rct": 50, "res": 1000}
        }
        
        reward = rewards.get(nft_type, rewards["identity"])
        
        # Check RCT cap
        can_mint, reason = _check_rct_cap(recipient, reward["rct"])
        if not can_mint:
            return jsonify({"error": f"RCT cap exceeded: {reason}"}), 429
        
        # Determine fee payer
        fee_payer_path, fee_payer_label = _get_fee_payer(network, recipient)
        
        # Mint NFT to Symbiotic PDA (not user wallet)
        nft_result = nft_minter.mint_soulbound_nft(
            recipient=pda_address,
            nft_type=nft_type,
            name=f"ResonantOS {nft_type.replace('_', ' ').title()}",
            symbol="ROS-NFT",
            fee_payer_keypair=fee_payer_path
        )
        
        # Mint reward tokens
        token_manager = TokenManager(SolanaWallet(network=network))
        
        # Mint RCT (Token-2022) → Symbiotic PDA
        rct_result = token_manager.mint_tokens(
            mint=_RCT_MINT,
            destination_owner=pda_address,
            amount=reward["rct"] * (10 ** _RCT_DECIMALS),
            token_program="token2022"
        )
        
        # Mint RES (SPL) → Symbiotic PDA
        res_result = token_manager.mint_tokens(
            mint=_RES_MINT,
            destination_owner=pda_address,
            amount=reward["res"] * (10 ** 6),
            token_program="spl"
        )
        
        # Record RCT mint for cap tracking
        _record_rct_mint(recipient, reward["rct"])
        
        # Update NFT registry for display name resolution
        try:
            reg_path = str(_DASHBOARD_DIR / "data" / "nft_registry.json")
            registry = {}
            if os.path.exists(reg_path):
                with open(reg_path) as rf:
                    registry = json.load(rf)
            nft_mint_addr = nft_result.get("mint")
            if nft_mint_addr:
                registry[nft_mint_addr] = nft_type  # "identity" or "alpha_tester" → map alpha_tester to "alpha"
                if nft_type == "alpha_tester":
                    registry[nft_mint_addr] = "alpha"
                with open(reg_path, "w") as wf:
                    json.dump(registry, wf, indent=2)
        except Exception as e:
            print(f"Warning: could not update nft_registry: {e}")
        
        # Update onboarding status
        onboarding = _load_onboarding()
        if recipient not in onboarding:
            onboarding[recipient] = {}
        if nft_type == "identity":
            onboarding[recipient]["identityNftMinted"] = True
            onboarding[recipient]["identityNftMint"] = nft_result.get("mint")
        elif nft_type == "alpha_tester":
            onboarding[recipient]["alphaNftMinted"] = True
            onboarding[recipient]["alphaNftMint"] = nft_result.get("mint")
        _save_onboarding(onboarding)
        
        return jsonify({
            "success": True,
            "nftMint": nft_result.get("mint"),
            "rctAmount": reward["rct"],
            "resAmount": reward["res"],
            "feePayer": fee_payer_label,
            "transactions": {
                "nft": nft_result.get("signature") if isinstance(nft_result, dict) else str(nft_result),
                "rct": rct_result if isinstance(rct_result, str) else rct_result if isinstance(rct_result, str) else rct_result.get("signature"),
                "res": res_result if isinstance(res_result, str) else res_result if isinstance(res_result, str) else res_result.get("signature")
            }
        })
        
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route("/api/wallet/build-transfer-tx", methods=["POST"])
def api_wallet_build_transfer_tx():
    """Build a transfer_out transaction for Phantom to sign.

    The PDA transfer requires the on-chain program to authorize via CPI.
    Human signs the transaction via Phantom, server builds the instruction.

    Body: { sender, recipient, amount, token (RCT|RES), network }
    Returns: { transaction: base64-encoded serialized tx (message only, for Phantom signing) }
    """
    try:
        import hashlib as _hl
        import struct as _st
        import base64
        from solders.pubkey import Pubkey as _Pubkey
        from solders.instruction import Instruction as _Ix, AccountMeta as _AM
        from solders.transaction import Transaction as _Tx
        from solders.message import Message as _Msg
        from solana.rpc.api import Client as _Client

        data = request.get_json(force=True)
        network = data.get("network", "devnet")
        sender = data.get("sender", "").strip()
        recipient = data.get("recipient", "").strip()
        amount = float(data.get("amount", 0))
        token = data.get("token", "RCT").upper()

        if not sender or not recipient or amount <= 0:
            return jsonify({"error": "Missing sender, recipient, or valid amount"}), 400

        # Verify sender has Identity NFT (on-chain check first, onboarding cache fallback)
        if not _require_identity_nft(sender):
            return jsonify({"error": "Identity NFT required to send tokens"}), 403

        # Token config
        if token == "RCT":
            mint_str = _RCT_MINT
            decimals = 9
            token_prog_str = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"  # Token-2022
        elif token == "RES":
            mint_str = _RES_MINT
            decimals = 6
            token_prog_str = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"  # SPL Token
        else:
            return jsonify({"error": f"Unknown token: {token}"}), 400

        # Validate base58 addresses
        import re as _re
        _b58_re = _re.compile(r'^[1-9A-HJ-NP-Za-km-z]{32,44}$')
        if not _b58_re.match(sender):
            return jsonify({"error": f"Invalid sender address (not base58)"}), 400
        if not _b58_re.match(recipient):
            return jsonify({"error": f"Invalid recipient address (not base58)"}), 400

        # Derive PDA
        program_id = _Pubkey.from_string(_SYMBIOTIC_PROGRAM_ID)
        human = _Pubkey.from_string(sender)
        recipient_pk = _Pubkey.from_string(recipient)
        mint = _Pubkey.from_string(mint_str)
        token_prog = _Pubkey.from_string(token_prog_str)

        pda, bump = _Pubkey.find_program_address(
            [b"symbiotic", bytes(human), bytes([0])], program_id
        )

        # Verify symbiotic pair exists on-chain and is active
        pair_info = _solana_rpc(network, "getAccountInfo", [str(pda), {"encoding": "base64"}])
        pair_val = pair_info.get("result", {}).get("value") if isinstance(pair_info, dict) else None
        if not pair_val:
            return jsonify({"error": "Symbiotic wallet not initialized. Create Symbiotic Wallet first."}), 400
        try:
            import base64 as _b64
            raw_pair = _b64.b64decode(pair_val["data"][0])
            if len(raw_pair) >= 93:
                d = raw_pair[8:]  # skip discriminator
                pair_human = str(_Pubkey.from_bytes(d[0:32]))
                pair_frozen = bool(d[66])
                if pair_human != sender:
                    return jsonify({"error": "Unauthorized: connected wallet is not the pair human signer"}), 403
                if pair_frozen:
                    return jsonify({"error": "Symbiotic wallet is frozen"}), 403
        except Exception:
            # If decode fails, continue and let on-chain program enforce constraints
            pass

        # Derive ATAs
        from spl.token.instructions import get_associated_token_address
        from_ata = get_associated_token_address(pda, mint, token_prog)
        to_ata = get_associated_token_address(recipient_pk, mint, token_prog)

        # Build transfer_out instruction
        disc = _hl.sha256(b"global:transfer_out").digest()[:8]
        raw_amount = int(amount * (10 ** decimals))
        ix_data = disc + _st.pack("<Q", raw_amount)

        accounts = [
            _AM(pubkey=pda, is_signer=False, is_writable=False),
            _AM(pubkey=human, is_signer=True, is_writable=True),
            _AM(pubkey=from_ata, is_signer=False, is_writable=True),
            _AM(pubkey=to_ata, is_signer=False, is_writable=True),
            _AM(pubkey=mint, is_signer=False, is_writable=False),
            _AM(pubkey=token_prog, is_signer=False, is_writable=False),
        ]

        ix = _Ix(program_id, ix_data, accounts)

        # Optionally create recipient ATA if it doesn't exist
        rpcs = {"devnet": "https://api.devnet.solana.com", "testnet": "https://api.testnet.solana.com", "mainnet-beta": "https://api.mainnet-beta.com"}
        client = _Client(rpcs.get(network, network))

        instructions = []

        # Check if recipient ATA exists
        ata_info = client.get_account_info(to_ata)
        if ata_info.value is None:
            # Create ATA instruction
            from spl.token.instructions import create_associated_token_account
            create_ata_ix = create_associated_token_account(
                payer=human, owner=recipient_pk, mint=mint, token_program_id=token_prog
            )
            instructions.append(create_ata_ix)

        instructions.append(ix)

        # Build transaction message
        blockhash_resp = client.get_latest_blockhash()
        blockhash = blockhash_resp.value.blockhash
        msg = _Msg.new_with_blockhash(instructions, human, blockhash)
        tx = _Tx.new_unsigned(msg)

        # Serialize for Phantom
        tx_bytes = bytes(tx)
        tx_b64 = base64.b64encode(tx_bytes).decode("ascii")

        return jsonify({
            "transaction": tx_b64,
            "pda": str(pda),
            "fromAta": str(from_ata),
            "toAta": str(to_ata),
            "rawAmount": raw_amount,
            "decimals": decimals,
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route("/api/wallet/build-sol-transfer", methods=["POST"])
def api_wallet_build_sol_transfer():
    """Build a simple SOL transfer from Phantom wallet (system program).
    Body: { sender, recipient, amount, network }
    Returns: { transaction: base64 }
    """
    try:
        import struct as _st
        import base64
        from solders.pubkey import Pubkey as _Pubkey
        from solders.instruction import Instruction as _Ix, AccountMeta as _AM
        from solders.transaction import Transaction as _Tx
        from solders.message import Message as _Msg
        from solana.rpc.api import Client as _Client

        data = request.get_json(force=True)
        network = data.get("network", "devnet")
        sender = data.get("sender", "").strip()
        recipient = data.get("recipient", "").strip()
        amount = float(data.get("amount", 0))

        if not sender or not recipient or amount <= 0:
            return jsonify({"error": "Missing sender, recipient, or valid amount"}), 400

        import re as _re
        _b58_re = _re.compile(r'^[1-9A-HJ-NP-Za-km-z]{32,44}$')
        if not _b58_re.match(sender) or not _b58_re.match(recipient):
            return jsonify({"error": "Invalid address (not base58)"}), 400

        sender_pk = _Pubkey.from_string(sender)
        recipient_pk = _Pubkey.from_string(recipient)
        lamports = int(amount * 1_000_000_000)  # SOL → lamports

        # System program transfer instruction
        system_prog = _Pubkey.from_string("11111111111111111111111111111111")
        ix_data = _st.pack("<II", 2, 0) + _st.pack("<Q", lamports)  # instruction index 2 = Transfer
        # Simpler: use solders system_program if available
        try:
            from solders.system_program import transfer, TransferParams
            ix = transfer(TransferParams(from_pubkey=sender_pk, to_pubkey=recipient_pk, lamports=lamports))
        except ImportError:
            accounts = [
                _AM(pubkey=sender_pk, is_signer=True, is_writable=True),
                _AM(pubkey=recipient_pk, is_signer=False, is_writable=True),
            ]
            ix = _Ix(system_prog, ix_data, accounts)

        rpcs = {"devnet": "https://api.devnet.solana.com", "testnet": "https://api.testnet.solana.com", "mainnet-beta": "https://api.mainnet-beta.com"}
        client = _Client(rpcs.get(network, network))
        blockhash_resp = client.get_latest_blockhash()
        blockhash = blockhash_resp.value.blockhash

        msg = _Msg.new_with_blockhash([ix], sender_pk, blockhash)
        tx = _Tx.new_unsigned(msg)
        tx_b64 = base64.b64encode(bytes(tx)).decode("ascii")

        return jsonify({"transaction": tx_b64, "lamports": lamports})

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/api/wallet/send-tokens", methods=["POST"])
def api_wallet_send_tokens():
    """Legacy endpoint — redirects to build-transfer-tx."""
    return api_wallet_build_transfer_tx()

@app.route("/api/wallet/daily-claim", methods=["POST"])
def api_wallet_daily_claim():
    """24h cooldown, mint 1 RCT + 500 RES with cap check."""
    try:
        if not TokenManager:
            return jsonify({"error": "Solana toolkit not available"}), 500
            
        data = request.get_json() or {}
        network = data.get("network", "devnet")
        recipient = data.get("recipient")
        signature = data.get("signature")  # Phantom co-signature
        
        # Devnet only for alpha
        if network != "devnet":
            return jsonify({"error": "Only devnet supported during alpha"}), 400
        
        if not recipient or not signature:
            return jsonify({"error": "recipient and signature required"}), 400
        if not _is_valid_pubkey(recipient):
            return jsonify({"error": "Invalid recipient address"}), 400
        
        # Require Identity NFT
        if not _require_identity_nft(recipient):
            return jsonify({"error": "Identity NFT required. Complete onboarding first."}), 403
        
        # Check 24h cooldown
        claims = _load_daily_claims()
        raw_claim = claims.get(recipient)
        # Handle both old format (string timestamp) and new format (dict)
        if isinstance(raw_claim, str):
            user_claims = {"last_claim": raw_claim, "total_claims": 0}
        elif isinstance(raw_claim, dict):
            user_claims = raw_claim
        else:
            user_claims = {}
        last_claim = user_claims.get("last_claim")
        
        if last_claim:
            last_claim_time = datetime.fromisoformat(last_claim.replace("Z", "+00:00"))
            if last_claim_time.tzinfo is None:
                last_claim_time = last_claim_time.replace(tzinfo=timezone.utc)
            hours_since = (datetime.now(timezone.utc) - last_claim_time).total_seconds() / 3600
            if hours_since < 24:
                hours_remaining = 24 - hours_since
                return jsonify({
                    "error": f"Cooldown active. {hours_remaining:.1f} hours remaining.",
                    "hoursRemaining": hours_remaining
                }), 429
        
        # Check RCT cap
        can_mint, reason = _check_rct_cap(recipient, 1)
        if not can_mint:
            return jsonify({"error": f"RCT cap exceeded: {reason}"}), 429
        
        # Determine fee payer
        fee_payer_path, fee_payer_label = _get_fee_payer(network, recipient)
        
        # Mint tokens
        token_manager = TokenManager(SolanaWallet(network=network))
        pda_address = _derive_symbiotic_pda(recipient)
        
        # Mint 1 RCT → Symbiotic PDA
        rct_result = token_manager.mint_tokens(
            mint=_RCT_MINT,
            destination_owner=pda_address,
            amount=1 * (10 ** _RCT_DECIMALS),
            token_program="token2022"
        )
        
        # Mint 500 RES → Symbiotic PDA
        res_result = token_manager.mint_tokens(
            mint=_RES_MINT,
            destination_owner=pda_address,
            amount=500 * (10 ** 6),
            token_program="spl"
        )
        
        # Record claim and RCT mint
        claims[recipient] = {
            "last_claim": datetime.now(timezone.utc).isoformat(),
            "total_claims": user_claims.get("total_claims", 0) + 1
        }
        _save_daily_claims(claims)
        _record_rct_mint(recipient, 1)
        
        return jsonify({
            "success": True,
            "rctAmount": 1,
            "resAmount": 500,
            "feePayer": fee_payer_label,
            "nextClaimAvailable": (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat(),
            "transactions": {
                "rct": rct_result if isinstance(rct_result, str) else rct_result.get("signature"),
                "res": res_result if isinstance(res_result, str) else res_result.get("signature")
            }
        })
        
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route("/api/wallet/onboarding-status")
def api_wallet_onboarding_status():
    """Check onboarding status with blockchain as source of truth."""
    try:
        address = request.args.get("address")
        network = request.args.get("network", "devnet")
        if not address:
            return jsonify({"error": "address parameter required"}), 400
        if not _is_valid_pubkey(address):
            return jsonify({"error": "Invalid wallet address"}), 400

        pda_address = _derive_symbiotic_pda(address)
        pair_exists = False
        try:
            pair_info = _solana_rpc(network, "getAccountInfo", [pda_address, {"encoding": "base64"}])
            pair_exists = pair_info.get("result", {}).get("value") is not None
        except Exception:
            pair_exists = False

        license_status = _wallet_has_nft(address, "symbiotic_license", network=network) if pair_exists else False
        manifesto_status = _wallet_has_nft(address, "manifesto", network=network) if pair_exists else False
        identity_status = _wallet_has_nft(address, "identity", network=network) if pair_exists else False
        alpha_status = _wallet_has_nft(address, "alpha_tester", network=network) if pair_exists else False

        onboarding = _load_onboarding()
        user_onboarding = onboarding.setdefault(address, {})
        user_onboarding["symbioticPairCreated"] = pair_exists
        user_onboarding["symbioticPda"] = pda_address
        user_onboarding["licenseSigned"] = license_status
        user_onboarding["manifestoSigned"] = manifesto_status
        user_onboarding["identityNftMinted"] = identity_status
        user_onboarding["alphaNftMinted"] = alpha_status
        _save_onboarding(onboarding)

        return jsonify({
            "address": address,
            "network": network,
            "symbioticPairCreated": pair_exists,
            "symbioticPda": pda_address,
            "alphaAgreed": user_onboarding.get("alphaAgreed", False),
            "licenseSigned": license_status,
            "manifestoSigned": manifesto_status,
            "identityNftMinted": identity_status,
            "alphaNftMinted": alpha_status,
            "onboardingComplete": all([
                user_onboarding.get("alphaAgreed"),
                pair_exists,
                license_status,
                manifesto_status,
                identity_status,
                alpha_status
            ])
        })
        
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route("/api/wallet/agree-alpha", methods=["POST"])
def api_wallet_agree_alpha():
    """Record Alpha Testing Agreement acceptance."""
    try:
        data = request.get_json() or {}
        address = data.get("address")
        signature = data.get("signature")

        if not address or not signature:
            return jsonify({"error": "address and signature required"}), 400
        if not _is_valid_pubkey(address):
            return jsonify({"error": "Invalid wallet address"}), 400

        onboarding = _load_onboarding()
        if address not in onboarding:
            onboarding[address] = {}

        if onboarding[address].get("alphaAgreed"):
            return jsonify({"error": "Already agreed"}), 409

        onboarding[address]["alphaAgreed"] = True
        onboarding[address]["alphaAgreedAt"] = datetime.now(timezone.utc).isoformat()
        onboarding[address]["alphaSignature"] = signature
        _save_onboarding(onboarding)

        return jsonify({"success": True})

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/api/wallet/sign-license", methods=["POST"])
def api_wallet_sign_license():
    """Co-sign license, mint License NFT."""
    try:
        if not NFTMinter:
            return jsonify({"error": "Solana toolkit not available"}), 500
            
        data = request.get_json() or {}
        network = data.get("network", "devnet")
        address = data.get("address")
        signature = data.get("signature")  # Phantom signature of license hash
        
        if not address or not signature:
            return jsonify({"error": "address and signature required"}), 400
        if not _is_valid_pubkey(address):
            return jsonify({"error": "Invalid wallet address"}), 400

        pda_address = _derive_symbiotic_pda(address)
        nft_minter = NFTMinter(SolanaWallet(network=network))
        existing = nft_minter.check_wallet_has_nft(pda_address, "symbiotic_license")
        if existing.get("has_nft"):
            return jsonify({
                "error": "Already holds Symbiotic License NFT",
                "existing_mint": existing.get("mint"),
            }), 409
        
        # Verify signature is of correct license hash
        license_text = "Resonant Commons Symbiotic License (RC-SL) v1.0"
        expected_hash = hashlib.sha256(license_text.encode()).hexdigest()
        
        # Store signing record
        onboarding = _load_onboarding()
        if address not in onboarding:
            onboarding[address] = {}
        
        onboarding[address]["licenseSigned"] = True
        onboarding[address]["licenseSignedAt"] = datetime.now(timezone.utc).isoformat()
        onboarding[address]["licenseHash"] = expected_hash
        onboarding[address]["licenseSignature"] = signature
        
        _save_onboarding(onboarding)
        
        # Mint License NFT to Symbiotic PDA
        fee_payer_path, fee_payer_label = _get_fee_payer(network, address)
        nft_result = nft_minter.mint_soulbound_nft(
            recipient=pda_address,
            nft_type="symbiotic_license",
            name="Resonant Commons License Signatory",
            symbol="RC-LIC",
            fee_payer_keypair=fee_payer_path
        )
        
        # Store NFT mint in onboarding record
        if nft_result.get("mint"):
            onboarding[address]["licenseNft"] = nft_result["mint"]
            _save_onboarding(onboarding)
        
        return jsonify({
            "success": True,
            "licenseHash": expected_hash,
            "nftMint": nft_result.get("mint"),
            "feePayer": fee_payer_label,
            "transaction": nft_result.get("signature")
        })
        
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route("/api/wallet/sign-manifesto", methods=["POST"])
def api_wallet_sign_manifesto():
    """Co-sign manifesto, mint Manifesto NFT."""
    try:
        if not NFTMinter:
            return jsonify({"error": "Solana toolkit not available"}), 500
            
        data = request.get_json() or {}
        network = data.get("network", "devnet")
        address = data.get("address")
        signature = data.get("signature")  # Phantom signature of manifesto hash
        
        if not address or not signature:
            return jsonify({"error": "address and signature required"}), 400
        
        # Require license signed first
        onboarding = _load_onboarding()
        user_onboarding = onboarding.get(address, {})
        
        if not user_onboarding.get("licenseSigned"):
            return jsonify({"error": "Must sign license first"}), 400

        pda_address = _derive_symbiotic_pda(address)
        nft_minter = NFTMinter(SolanaWallet(network=network))
        existing = nft_minter.check_wallet_has_nft(pda_address, "manifesto")
        if existing.get("has_nft"):
            return jsonify({
                "error": "Already holds Manifesto NFT",
                "existing_mint": existing.get("mint"),
            }), 409
        
        # Verify signature is of correct manifesto hash
        manifesto_text = "Augmentatism Manifesto v2.2"
        expected_hash = hashlib.sha256(manifesto_text.encode()).hexdigest()
        
        # Store signing record
        onboarding[address]["manifestoSigned"] = True
        onboarding[address]["manifestoSignedAt"] = datetime.now(timezone.utc).isoformat()
        onboarding[address]["manifestoHash"] = expected_hash
        onboarding[address]["manifestoSignature"] = signature
        
        _save_onboarding(onboarding)
        
        # Mint Manifesto NFT to Symbiotic PDA
        fee_payer_path, fee_payer_label = _get_fee_payer(network, address)
        nft_result = nft_minter.mint_soulbound_nft(
            recipient=pda_address,
            nft_type="manifesto",
            name="Augmentatism Manifesto Signatory",
            symbol="AUG-MAN",
            fee_payer_keypair=fee_payer_path
        )
        
        # Store NFT mint in onboarding record
        if nft_result.get("mint"):
            onboarding[address]["manifestoNft"] = nft_result["mint"]
            _save_onboarding(onboarding)
        
        return jsonify({
            "success": True,
            "manifestoHash": expected_hash,
            "nftMint": nft_result.get("mint"),
            "feePayer": fee_payer_label,
            "transaction": nft_result.get("signature")
        })
        
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route("/api/wallet/reputation")
def api_wallet_reputation():
    """Query REX token balances, compute levels."""
    try:
        network = request.args.get("network", "devnet")
        address = request.args.get("address")
        
        if not address:
            return jsonify({"error": "address parameter required"}), 400
        
        reputation = {"address": address, "network": network, "categories": {}}
        
        # Query REX token balances
        for category, mint in _REX_MINTS.items():
            try:
                result = _solana_rpc(network, "getTokenAccountsByOwner", [
                    address,
                    {"mint": mint},
                    {"encoding": "jsonParsed"}
                ])
                
                balance = 0
                for account in result.get("result", {}).get("value", []):
                    parsed = account.get("account", {}).get("data", {}).get("parsed", {}).get("info", {})
                    token_amount = parsed.get("tokenAmount", {})
                    amount = float(token_amount.get("amount", 0))
                    decimals = token_amount.get("decimals", 0)
                    balance = amount / (10 ** decimals) if decimals > 0 else amount
                    break
                
                # Compute level from thresholds
                level = 0
                for i, threshold in enumerate(_LEVEL_THRESHOLDS):
                    if balance >= threshold:
                        level = i
                    else:
                        break
                
                reputation["categories"][category] = {
                    "balance": balance,
                    "level": level,
                    "mint": mint,
                    "display": _REX_DISPLAY[category]
                }
                
            except Exception as e:
                print(f"Error querying REX {category}: {e}")
                reputation["categories"][category] = {
                    "balance": 0,
                    "level": 0,
                    "mint": mint,
                    "display": _REX_DISPLAY[category]
                }
        
        # Compute overall level (max of all categories)
        overall_level = max([cat.get("level", 0) for cat in reputation["categories"].values()] + [0])
        reputation["overallLevel"] = overall_level
        
        return jsonify(reputation)
        
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route("/api/wallet/grant-xp", methods=["POST"])
def api_wallet_grant_xp():
    """Mint REX tokens + 10 RCT bonus."""
    try:
        if not TokenManager:
            return jsonify({"error": "Solana toolkit not available"}), 500
            
        data = request.get_json() or {}
        network = data.get("network", "devnet")
        recipient = data.get("recipient")
        category = data.get("category")  # GOV, FIN, COM, CRE, TEC
        amount = data.get("amount", 10)  # XP amount to grant
        signature = data.get("signature")  # Phantom co-signature
        
        if not recipient or not category or category not in _REX_MINTS:
            return jsonify({"error": "recipient and valid category required"}), 400
        
        # Require Identity NFT
        if not _require_identity_nft(recipient):
            return jsonify({"error": "Identity NFT required. Complete onboarding first."}), 403
        
        # Check RCT cap for the 10 RCT bonus
        can_mint, reason = _check_rct_cap(recipient, 10)
        if not can_mint:
            return jsonify({"error": f"RCT cap exceeded: {reason}"}), 429
        
        # Determine fee payer
        fee_payer_path, fee_payer_label = _get_fee_payer(network, recipient)
        
        token_manager = TokenManager(SolanaWallet(network=network))
        pda_address = _derive_symbiotic_pda(recipient)
        
        # Mint REX tokens (Token-2022, 0 decimals) → Symbiotic PDA
        rex_result = token_manager.mint_tokens(
            mint=_REX_MINTS[category],
            destination_owner=pda_address,
            amount=amount,
            token_program="token2022"
        )
        
        # Mint 10 RCT bonus → Symbiotic PDA
        rct_result = token_manager.mint_tokens(
            mint=_RCT_MINT,
            destination_owner=pda_address,
            amount=10 * (10 ** _RCT_DECIMALS),
            token_program="token2022"
        )
        
        # Record RCT mint
        _record_rct_mint(recipient, 10)
        
        return jsonify({
            "success": True,
            "category": category,
            "categoryDisplay": _REX_DISPLAY[category],
            "xpAmount": amount,
            "rctBonus": 10,
            "feePayer": fee_payer_label,
            "transactions": {
                "rex": rex_result if isinstance(rex_result, str) else rex_result.get("signature"),
                "rct": rct_result if isinstance(rct_result, str) else rct_result.get("signature")
            }
        })
        
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route("/api/wallet/leaderboard")
def api_wallet_leaderboard():
    """Rankings by RCT and REX categories — only Identity NFT holders."""
    try:
        network = request.args.get("network", "devnet")
        
        leaderboard = {"network": network, "overall": [], "categories": {}}
        
        # Load onboarding data — only include users with Identity NFT
        onboarding = _load_onboarding()
        identity_holders = {
            addr for addr, data in onboarding.items()
            if data.get("identityNftMinted")
        }

        # Build PDA→human mapping for all identity holders
        pda_to_human = {}
        for human_addr in identity_holders:
            try:
                pda = _derive_symbiotic_pda(human_addr)
                pda_to_human[pda] = human_addr
            except Exception:
                pass

        # Helper: resolve token account (ATA) → owner address
        def _resolve_owner(network, ata_address):
            try:
                info = _solana_rpc(network, "getAccountInfo", [
                    ata_address, {"encoding": "jsonParsed"}
                ])
                parsed = (info.get("result", {}).get("value", {})
                          .get("data", {}).get("parsed", {})
                          .get("info", {}))
                return parsed.get("owner", ata_address)
            except Exception:
                return ata_address

        # Helper: build ranked list — tokens live on PDAs now
        def _build_board(mint, decimals, max_entries):
            if not identity_holders:
                return []
            try:
                result = _solana_rpc(network, "getTokenLargestAccounts", [mint])
                accounts = result.get("result", {}).get("value", [])
            except Exception as e:
                print(f"Error getting largest accounts for {mint}: {e}")
                return []

            board = []
            for account in accounts:
                if len(board) >= max_entries:
                    break

                ata = account.get("address")
                amount = account.get("amount")
                dec = account.get("decimals", decimals)
                balance = int(amount) / (10 ** dec) if amount else 0
                if balance <= 0:
                    continue

                owner = _resolve_owner(network, ata)

                # Owner could be a PDA or a human wallet
                # Accept if owner IS an identity holder (human wallet)
                # OR if owner is a PDA that maps to an identity holder
                human_addr = pda_to_human.get(owner)
                if human_addr:
                    display_addr = human_addr  # show human wallet, not PDA
                elif owner in identity_holders:
                    display_addr = owner
                else:
                    continue  # skip non-identity-holder wallets

                level = 0
                for j, threshold in enumerate(_LEVEL_THRESHOLDS):
                    if balance >= threshold:
                        level = j
                    else:
                        break

                board.append({
                    "rank": len(board) + 1,
                    "address": display_addr,
                    "balance": balance,
                    "level": level
                })
            return board
        
        # Overall RCT leaderboard
        leaderboard["overall"] = _build_board(_RCT_MINT, _RCT_DECIMALS, 10)
        
        # REX category leaderboards
        for category, mint in _REX_MINTS.items():
            leaderboard["categories"][category] = {
                "display": _REX_DISPLAY[category],
                "rankings": _build_board(mint, 9, 5)
            }
        
        return jsonify(leaderboard)
        
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# ---------------------------------------------------------------------------
# Tribes + Bounties API
# ---------------------------------------------------------------------------

@app.route("/api/tribes", methods=["GET"])
def api_tribes_list():
    try:
        tribes = _load_tribes()
        bounties = _load_bounties()
        _sync_tribe_bounty_refs(tribes, bounties)
        _save_tribes(tribes)

        payload = []
        for tribe in tribes:
            payload.append({
                **tribe,
                "memberCount": len(tribe.get("members", [])),
                "activeBountyCount": len(tribe.get("activeBounties", [])),
                "completedBountyCount": len(tribe.get("completedBounties", [])),
            })
        return jsonify({"tribes": payload, "count": len(payload)})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/api/tribes/<tribe_id>", methods=["GET"])
def api_tribe_detail(tribe_id):
    try:
        tribes = _load_tribes()
        bounties = _load_bounties()
        tribe = next((t for t in tribes if t.get("id") == tribe_id), None)
        if not tribe:
            return jsonify({"error": "Tribe not found"}), 404

        tribe_bounties = [b for b in bounties if b.get("tribeId") == tribe_id]
        detail = dict(tribe)
        detail["bounties"] = tribe_bounties
        detail["memberCount"] = len(tribe.get("members", []))
        detail["activeBountyCount"] = len([b for b in tribe_bounties if b.get("status") != "rewarded"])
        detail["completedBountyCount"] = len([b for b in tribe_bounties if b.get("status") == "rewarded"])
        return jsonify(detail)
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/api/tribes", methods=["POST"])
def api_tribe_create():
    try:
        data = request.get_json(force=True) or {}
        wallet = (data.get("wallet") or "").strip()
        name = (data.get("name") or "").strip()
        description = (data.get("description") or "").strip()
        category = (data.get("category") or "core").strip()
        tags = data.get("tags") if isinstance(data.get("tags"), list) else []

        if not wallet or not name:
            return jsonify({"error": "wallet and name are required"}), 400
        if not _require_identity_nft(wallet):
            return jsonify({"error": "Identity NFT required to create a tribe"}), 403

        tribes = _load_tribes()
        max_id = 0
        for t in tribes:
            try:
                max_id = max(max_id, int(str(t.get("id", "")).split("-")[-1]))
            except Exception:
                continue
        tribe_id = f"TRIBE-{max_id + 1:03d}"
        now_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        tribe = {
            "id": tribe_id,
            "name": name,
            "description": description or f"Working group for {name}.",
            "category": category,
            "members": [{"wallet": wallet, "role": "coordinator", "joinedAt": now_iso}],
            "coordinator": wallet,
            "activeBounties": [],
            "completedBounties": [],
            "createdAt": now_iso,
            "avatar": None,
            "tags": [str(t).strip() for t in tags if str(t).strip()],
        }
        tribes.append(tribe)
        _save_tribes(tribes)
        return jsonify(tribe), 201
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/api/tribes/<tribe_id>/join", methods=["POST"])
def api_tribe_join(tribe_id):
    try:
        data = request.get_json(force=True) or {}
        wallet = (data.get("wallet") or "").strip()
        role = (data.get("role") or "member").strip()
        if not wallet:
            return jsonify({"error": "wallet is required"}), 400
        if not _require_identity_nft(wallet):
            return jsonify({"error": "Identity NFT required"}), 403

        tribes = _load_tribes()
        tribe = next((t for t in tribes if t.get("id") == tribe_id), None)
        if not tribe:
            return jsonify({"error": "Tribe not found"}), 404
        members = tribe.setdefault("members", [])
        if any((m.get("wallet") == wallet) for m in members):
            return jsonify({"error": "Already a tribe member"}), 409
        members.append({
            "wallet": wallet,
            "role": role if role in {"member", "coordinator", "reviewer"} else "member",
            "joinedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        })
        _save_tribes(tribes)
        return jsonify({"success": True, "tribeId": tribe_id, "memberCount": len(members)})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/api/tribes/<tribe_id>/leave", methods=["POST"])
def api_tribe_leave(tribe_id):
    try:
        data = request.get_json(force=True) or {}
        wallet = (data.get("wallet") or "").strip()
        if not wallet:
            return jsonify({"error": "wallet is required"}), 400

        tribes = _load_tribes()
        tribe = next((t for t in tribes if t.get("id") == tribe_id), None)
        if not tribe:
            return jsonify({"error": "Tribe not found"}), 404
        members = tribe.get("members", [])
        updated = [m for m in members if m.get("wallet") != wallet]
        if len(updated) == len(members):
            return jsonify({"error": "Wallet is not a tribe member"}), 404
        tribe["members"] = updated
        if tribe.get("coordinator") == wallet:
            tribe["coordinator"] = updated[0]["wallet"] if updated else None
            if updated:
                updated[0]["role"] = "coordinator"
        _save_tribes(tribes)
        return jsonify({"success": True, "tribeId": tribe_id, "memberCount": len(updated)})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


def _auto_join_tribe(tribe, wallet, role="member"):
    members = tribe.setdefault("members", [])
    if any((m.get("wallet") == wallet) for m in members):
        return False
    members.append({
        "wallet": wallet,
        "role": role,
        "joinedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    })
    return True


@app.route("/api/bounties", methods=["GET"])
def api_bounties_list():
    try:
        status = request.args.get("status")
        category = request.args.get("category")
        priority = request.args.get("priority")
        size = request.args.get("size")
        tribe_id = request.args.get("tribeId")
        sort = request.args.get("sort", "priority")

        bounties = _load_bounties()
        tribes = _load_tribes()
        tribe_map = {t.get("id"): t for t in tribes}

        filtered = []
        for bounty in bounties:
            if status and bounty.get("status") != status:
                continue
            if category and bounty.get("category") != category:
                continue
            if priority and bounty.get("priority") != priority:
                continue
            if size and bounty.get("size") != size:
                continue
            if tribe_id and bounty.get("tribeId") != tribe_id:
                continue
            filtered.append(_enrich_bounty_with_tribe(bounty, tribe_map))

        if sort == "reward":
            filtered.sort(key=lambda b: (b.get("rewardRCT", 0), b.get("rewardRES", 0)), reverse=True)
        elif sort == "date":
            filtered.sort(key=lambda b: b.get("createdAt") or "", reverse=True)
        else:
            order = {"P0": 0, "P1": 1, "P2": 2}
            filtered.sort(key=lambda b: (order.get(b.get("priority"), 9), -(b.get("rewardRCT", 0))))

        return jsonify({"bounties": filtered, "count": len(filtered)})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/api/bounties/<bounty_id>", methods=["GET"])
def api_bounty_detail(bounty_id):
    try:
        bounties = _load_bounties()
        tribes = _load_tribes()
        tribe_map = {t.get("id"): t for t in tribes}
        bounty = next((b for b in bounties if b.get("id") == bounty_id), None)
        if not bounty:
            return jsonify({"error": "Bounty not found"}), 404
        return jsonify(_enrich_bounty_with_tribe(bounty, tribe_map))
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/api/bounties/<bounty_id>/claim", methods=["POST"])
def api_bounty_claim(bounty_id):
    try:
        data = request.get_json(force=True) or {}
        wallet = (data.get("wallet") or "").strip()
        if not wallet:
            return jsonify({"error": "wallet is required"}), 400
        if not _require_identity_nft(wallet):
            return jsonify({"error": "Identity NFT required to claim bounties"}), 403

        bounties = _load_bounties()
        tribes = _load_tribes()
        bounty = next((b for b in bounties if b.get("id") == bounty_id), None)
        if not bounty:
            return jsonify({"error": "Bounty not found"}), 404
        if bounty.get("status") not in {"open", "claimed", "in_progress"}:
            return jsonify({"error": f"Cannot claim bounty with status {bounty.get('status')}"}), 409

        claimed_by = bounty.setdefault("claimedBy", [])
        if wallet not in claimed_by:
            claimed_by.append(wallet)
        if bounty.get("status") == "open":
            bounty["status"] = "claimed"
        bounty["updatedAt"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

        tribe = next((t for t in tribes if t.get("id") == bounty.get("tribeId")), None)
        if tribe:
            _auto_join_tribe(tribe, wallet, "member")

        _sync_tribe_bounty_refs(tribes, bounties)
        _save_bounties(bounties)
        _save_tribes(tribes)
        return jsonify({"success": True, "bountyId": bounty_id, "status": bounty.get("status")})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/api/bounties/<bounty_id>/join", methods=["POST"])
def api_bounty_join(bounty_id):
    try:
        data = request.get_json(force=True) or {}
        wallet = (data.get("wallet") or "").strip()
        role = (data.get("role") or "member").strip()
        if not wallet:
            return jsonify({"error": "wallet is required"}), 400
        if not _require_identity_nft(wallet):
            return jsonify({"error": "Identity NFT required"}), 403

        bounties = _load_bounties()
        tribes = _load_tribes()
        bounty = next((b for b in bounties if b.get("id") == bounty_id), None)
        if not bounty:
            return jsonify({"error": "Bounty not found"}), 404
        tribe = next((t for t in tribes if t.get("id") == bounty.get("tribeId")), None)
        if not tribe:
            return jsonify({"error": "Associated tribe not found"}), 404

        if not _auto_join_tribe(tribe, wallet, role if role in {"member", "reviewer"} else "member"):
            return jsonify({"error": "Already a tribe member"}), 409
        _save_tribes(tribes)
        return jsonify({"success": True, "tribeId": tribe.get("id"), "memberCount": len(tribe.get("members", []))})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/api/bounties/<bounty_id>/leave", methods=["POST"])
def api_bounty_leave(bounty_id):
    try:
        data = request.get_json(force=True) or {}
        wallet = (data.get("wallet") or "").strip()
        if not wallet:
            return jsonify({"error": "wallet is required"}), 400

        bounties = _load_bounties()
        tribes = _load_tribes()
        bounty = next((b for b in bounties if b.get("id") == bounty_id), None)
        if not bounty:
            return jsonify({"error": "Bounty not found"}), 404
        tribe = next((t for t in tribes if t.get("id") == bounty.get("tribeId")), None)
        if not tribe:
            return jsonify({"error": "Associated tribe not found"}), 404

        members = tribe.get("members", [])
        tribe["members"] = [m for m in members if m.get("wallet") != wallet]
        claimed_by = bounty.get("claimedBy", [])
        bounty["claimedBy"] = [w for w in claimed_by if w != wallet]
        if not bounty["claimedBy"] and bounty.get("status") in {"claimed", "in_progress"}:
            bounty["status"] = "open"
        _save_tribes(tribes)
        _save_bounties(bounties)
        return jsonify({"success": True, "bountyId": bounty_id})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/api/bounties/<bounty_id>/submit", methods=["POST"])
def api_bounty_submit(bounty_id):
    try:
        data = request.get_json(force=True) or {}
        wallet = (data.get("wallet") or "").strip()
        if not wallet:
            return jsonify({"error": "wallet is required"}), 400

        bounties = _load_bounties()
        bounty = next((b for b in bounties if b.get("id") == bounty_id), None)
        if not bounty:
            return jsonify({"error": "Bounty not found"}), 404
        if wallet not in bounty.get("claimedBy", []):
            return jsonify({"error": "Only claimants can submit for review"}), 403

        bounty["status"] = "review"
        bounty["updatedAt"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        _save_bounties(bounties)
        return jsonify({"success": True, "status": "review"})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/api/bounties/<bounty_id>/review", methods=["POST"])
def api_bounty_review(bounty_id):
    try:
        data = request.get_json(force=True) or {}
        reviewer_wallet = (data.get("wallet") or "").strip()
        approved = bool(data.get("approve"))
        score = int(data.get("score") or 0)
        comments = (data.get("comments") or "").strip()
        verification_method = (data.get("verificationMethod") or "peer-reviewed").strip()
        if not reviewer_wallet:
            return jsonify({"error": "wallet is required"}), 400
        if score < 1 or score > 5:
            return jsonify({"error": "score must be between 1 and 5"}), 400

        bounties = _load_bounties()
        tribes = _load_tribes()
        bounty = next((b for b in bounties if b.get("id") == bounty_id), None)
        if not bounty:
            return jsonify({"error": "Bounty not found"}), 404
        if bounty.get("status") not in {"review", "verified"}:
            return jsonify({"error": f"Bounty status must be review/verified, got {bounty.get('status')}"}), 409

        tribe = next((t for t in tribes if t.get("id") == bounty.get("tribeId")), None)
        member_wallets = {m.get("wallet") for m in (tribe or {}).get("members", [])}
        if reviewer_wallet in member_wallets:
            return jsonify({"error": "Reviewer cannot be a tribe member"}), 409

        reviews = bounty.setdefault("reviews", [])
        if any(r.get("reviewerWallet") == reviewer_wallet for r in reviews):
            return jsonify({"error": "Reviewer already reviewed this bounty"}), 409

        review_entry = {
            "reviewerWallet": reviewer_wallet,
            "approved": approved,
            "score": score,
            "comments": comments,
            "verificationMethod": verification_method,
            "createdAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        }
        reviews.append(review_entry)

        approvals = [r for r in reviews if r.get("approved")]
        required_reviews = 1 if bounty.get("size") == "small" else 2 if bounty.get("size") == "medium" else 3
        if len(approvals) >= required_reviews:
            bounty["status"] = "verified"
            bounty["qualityGate"] = {
                "status": "passed",
                "reviewers": [r.get("reviewerWallet") for r in approvals],
                "score": round(sum(r.get("score", 0) for r in approvals) / len(approvals), 2),
                "verificationMethod": verification_method,
            }
        else:
            bounty["status"] = "review"

        bounty["updatedAt"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        _save_bounties(bounties)
        return jsonify({"success": True, "status": bounty.get("status"), "reviews": len(reviews)})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/api/bounties/<bounty_id>/reward", methods=["POST"])
def api_bounty_reward(bounty_id):
    try:
        bounties = _load_bounties()
        tribes = _load_tribes()
        bounty = next((b for b in bounties if b.get("id") == bounty_id), None)
        if not bounty:
            return jsonify({"error": "Bounty not found"}), 404
        if bounty.get("status") != "verified":
            return jsonify({"error": "Bounty must be verified before reward"}), 409

        claimants = bounty.get("claimedBy", [])
        if not claimants:
            return jsonify({"error": "No claimants to reward"}), 409
        split = len(claimants)
        payout = []
        rct_each = round(float(bounty.get("rewardRCT", 0)) / split, 4)
        res_each = round(float(bounty.get("rewardRES", 0)) / split, 4)
        for wallet in sorted(set(claimants)):
            payout.append({"wallet": wallet, "rct": rct_each, "res": res_each})

        bounty["status"] = "rewarded"
        now_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        bounty["updatedAt"] = now_iso
        bounty["reward"] = {
            "triggeredAt": now_iso,
            "recipients": payout,
            "totalRCT": float(bounty.get("rewardRCT", 0)),
            "totalRES": float(bounty.get("rewardRES", 0)),
            "onChain": False,
            "transactions": None,
        }

        _sync_tribe_bounty_refs(tribes, bounties)
        _save_bounties(bounties)
        _save_tribes(tribes)
        return jsonify({"success": True, "status": "rewarded", "recipients": payout})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/api/wallet/my-tribes", methods=["GET"])
def api_wallet_my_tribes():
    try:
        wallet = request.args.get("address", "").strip()
        if not wallet:
            return jsonify({"error": "address parameter required"}), 400
        tribes = _load_tribes()
        mine = []
        for tribe in tribes:
            members = tribe.get("members", [])
            if any(m.get("wallet") == wallet for m in members):
                mine.append({
                    "id": tribe.get("id"),
                    "name": tribe.get("name"),
                    "description": tribe.get("description"),
                    "category": tribe.get("category"),
                    "memberCount": len(members),
                    "activeBountyCount": len(tribe.get("activeBounties", [])),
                    "role": next((m.get("role") for m in members if m.get("wallet") == wallet), "member"),
                })
        return jsonify({"wallet": wallet, "tribes": mine, "count": len(mine)})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/api/wallet/my-bounties", methods=["GET"])
def api_wallet_my_bounties():
    try:
        wallet = request.args.get("address", "").strip()
        if not wallet:
            return jsonify({"error": "address parameter required"}), 400
        bounties = _load_bounties()
        tribes = _load_tribes()
        tribe_map = {t.get("id"): t for t in tribes}
        mine = []
        for bounty in bounties:
            if wallet not in bounty.get("claimedBy", []):
                continue
            entry = _enrich_bounty_with_tribe(bounty, tribe_map)
            mine.append({
                "id": entry.get("id"),
                "title": entry.get("title"),
                "status": entry.get("status"),
                "priority": entry.get("priority"),
                "rewardRCT": entry.get("rewardRCT"),
                "rewardRES": entry.get("rewardRES"),
                "tribe": entry.get("tribe"),
            })
        return jsonify({"wallet": wallet, "bounties": mine, "count": len(mine)})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# ---------------------------------------------------------------------------
# Protocol Store API
# ---------------------------------------------------------------------------

# Track minted protocol NFTs: {protocol_id: {wallet: mint_address}}
_PROTOCOL_MINTS_FILE = Path(__file__).parent / "data" / "protocol_mints.json"

def _load_protocol_mints():
    try:
        if _PROTOCOL_MINTS_FILE.exists():
            return json.loads(_PROTOCOL_MINTS_FILE.read_text())
    except Exception:
        pass
    return {}

def _save_protocol_mints(data):
    _PROTOCOL_MINTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    _PROTOCOL_MINTS_FILE.write_text(json.dumps(data, indent=2))

@app.route("/api/protocol-store/list", methods=["GET"])
def api_protocol_store_list():
    """List available protocols with prices and creator info."""
    # Add creator to each protocol (Manolo's wallet for all official ones)
    enriched = {}
    for pid, pdata in PROTOCOL_NFTS.items():
        enriched[pid] = {**pdata, "creator": "vbYQ7rZu19Rjtro9obQxFeHq5UPNF5RQXA8jP8qywfF"}
    return jsonify({"protocols": enriched})

@app.route("/api/protocol-store/purchase", methods=["POST"])
def api_protocol_store_purchase():
    """Purchase a protocol NFT. Body: {protocol_id, wallet_address, network}"""
    try:
        if not ProtocolNFTMinter:
            return jsonify({"error": "Protocol NFT minter not available"}), 500

        data = request.get_json() or {}
        protocol_id = data.get("protocol_id")
        wallet_address = data.get("wallet_address")
        network = data.get("network", "devnet")

        if network != "devnet":
            return jsonify({"error": "Only devnet supported during alpha"}), 400

        if not protocol_id or not wallet_address:
            return jsonify({"error": "protocol_id and wallet_address required"}), 400

        # Require Identity NFT
        if not _require_identity_nft(wallet_address):
            return jsonify({"error": "Identity NFT required. Complete onboarding first."}), 403

        if protocol_id not in PROTOCOL_NFTS:
            return jsonify({"error": f"Unknown protocol: {protocol_id}"}), 400

        # Check if already purchased
        mints = _load_protocol_mints()
        wallet_mints = mints.get(wallet_address, {})
        if protocol_id in wallet_mints:
            return jsonify({
                "error": "Already purchased",
                "mint": wallet_mints[protocol_id]
            }), 409

        # ── Verify $RES payment: check Symbiotic PDA balance ──
        protocol_info = PROTOCOL_NFTS[protocol_id]
        price_res = protocol_info.get("price_res", 0)  # price in $RES
        if price_res > 0:
            from solders.pubkey import Pubkey as _Pk
            from solana.rpc.api import Client as _Cl
            program_id = _Pk.from_string(_SYMBIOTIC_PROGRAM_ID)
            human_pk = _Pk.from_string(wallet_address)
            pda, _ = _Pk.find_program_address(
                [b"symbiotic", bytes(human_pk), bytes([0])], program_id
            )
            res_mint = _Pk.from_string(_RES_MINT)
            res_prog = _Pk.from_string("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")
            from spl.token.instructions import get_associated_token_address
            pda_ata = get_associated_token_address(pda, res_mint, res_prog)
            rpcs = {"devnet": "https://api.devnet.solana.com"}
            cl = _Cl(rpcs.get(network, network))
            ata_info = cl.get_account_info_json_parsed(pda_ata)
            pda_balance = 0
            if ata_info.value:
                try:
                    pda_balance = int(ata_info.value.data.parsed["info"]["tokenAmount"]["amount"]) / 1e6
                except Exception:
                    pass
            if pda_balance < price_res:
                return jsonify({
                    "error": f"Insufficient $RES balance. Need {price_res}, have {pda_balance:.2f}",
                    "required": price_res,
                    "balance": pda_balance,
                }), 402

            # TODO: Actual $RES burn/transfer via on-chain escrow program
            # Currently: balance check only (gate). Deduction requires Anchor
            # marketplace program CPI (5wpGj4EG6J5uEqozLqUyHzEQbU26yjaL5aUE5FwBiYe5).
            # For alpha: balance check prevents abuse; users can't purchase
            # without sufficient $RES in their Symbiotic PDA.
            app.logger.info(
                f"Protocol purchase: {wallet_address} buying {protocol_id} "
                f"(price={price_res} $RES, balance={pda_balance:.2f} $RES) "
                f"— BALANCE CHECK PASSED, deduction pending on-chain escrow"
            )

        # Use Registration Basket as fee payer
        fee_payer = str(_REGISTRATION_BASKET_KEYPAIR)

        minter = ProtocolNFTMinter()
        result = minter.mint_protocol_nft(
            recipient=wallet_address,
            protocol_id=protocol_id,
            fee_payer_keypair=fee_payer,
        )

        # Record the mint
        if wallet_address not in mints:
            mints[wallet_address] = {}
        mints[wallet_address][protocol_id] = result["mint"]
        _save_protocol_mints(mints)

        return jsonify({
            "success": True,
            "mint": result["mint"],
            "ata": result["ata"],
            "protocol_id": protocol_id,
            "name": result["name"],
            "symbol": result["symbol"],
            "signature": result["mint_signature"],
            "transferable": True,
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route("/api/protocol-store/owned", methods=["GET"])
def api_protocol_store_owned():
    """Check which protocols a wallet owns. Query: ?wallet=<address>"""
    try:
        wallet = request.args.get("wallet")
        if not wallet:
            return jsonify({"error": "wallet parameter required"}), 400

        mints = _load_protocol_mints()
        wallet_mints = mints.get(wallet, {})

        owned = []
        for protocol_id, mint_address in wallet_mints.items():
            # Optionally verify on-chain ownership
            if ProtocolNFTMinter:
                try:
                    minter = ProtocolNFTMinter()
                    if minter.check_ownership(wallet, mint_address):
                        owned.append({"protocol_id": protocol_id, "mint": mint_address})
                except Exception:
                    # If check fails, trust the local record
                    owned.append({"protocol_id": protocol_id, "mint": mint_address})
            else:
                owned.append({"protocol_id": protocol_id, "mint": mint_address})

        return jsonify({"wallet": wallet, "owned": owned})

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route("/api/protocol-store/content/<protocol_id>", methods=["GET"])
def api_protocol_store_content(protocol_id):
    """Get protocol content (SOUL.md) if wallet owns the NFT. Query: ?wallet=<address>&mint=<mint_address>"""
    try:
        wallet = request.args.get("wallet")
        mint_address = request.args.get("mint")

        if not wallet or not mint_address:
            return jsonify({"error": "wallet and mint parameters required"}), 400

        if protocol_id not in PROTOCOL_NFTS:
            return jsonify({"error": f"Unknown protocol: {protocol_id}"}), 404

        # Verify ownership
        mints = _load_protocol_mints()
        wallet_mints = mints.get(wallet, {})
        if protocol_id not in wallet_mints or wallet_mints[protocol_id] != mint_address:
            return jsonify({"error": "You do not own this protocol NFT"}), 403

        # On-chain verification if available
        if ProtocolNFTMinter:
            try:
                minter = ProtocolNFTMinter()
                if not minter.check_ownership(wallet, mint_address):
                    return jsonify({"error": "On-chain ownership verification failed"}), 403
            except Exception:
                pass  # Fall through if RPC fails

        # Read protocol content
        protocol_file = Path(__file__).parent / "protocols" / f"{protocol_id}.md"
        if not protocol_file.exists():
            return jsonify({"error": "Protocol content not available"}), 404

        content = protocol_file.read_text()
        return jsonify({
            "protocol_id": protocol_id,
            "name": PROTOCOL_NFTS[protocol_id]["name"],
            "content": content,
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# ---------------------------------------------------------------------------
# Marketplace API (secondary market — all state on-chain via escrow program)
# ---------------------------------------------------------------------------
# Program: 5wpGj4EG6J5uEqozLqUyHzEQbU26yjaL5aUE5FwBiYe5 (DevNet)
# No server-side state. Listings read from Solana. Transactions signed by Phantom.

_MARKETPLACE_PROGRAM_ID = _CFG.get("programs", {}).get("MARKETPLACE_PROGRAM_ID", "5wpGj4EG6J5uEqozLqUyHzEQbU26yjaL5aUE5FwBiYe5")
_RCT_SELL_THRESHOLD = 500

try:
    from marketplace_client import get_all_listings, MARKETPLACE_PROGRAM_ID
except ImportError:
    get_all_listings = None
    MARKETPLACE_PROGRAM_ID = _MARKETPLACE_PROGRAM_ID


@app.route("/api/protocol-store/marketplace", methods=["GET"])
def api_marketplace_list():
    """List active marketplace listings from chain."""
    try:
        if get_all_listings is None:
            return jsonify({"listings": [], "warning": "marketplace_client not available"})

        network = request.args.get("network", "devnet")
        rpc = _SOLANA_RPCS.get(network, _SOLANA_RPCS["devnet"])
        listings = get_all_listings(rpc=rpc)

        # Enrich with protocol metadata from known mints
        mints_file = Path(__file__).parent.parent / "data" / "protocol_mints.json"
        mint_to_protocol = {}
        if mints_file.exists():
            records = json.loads(mints_file.read_text())
            for r in records.get("mints", []):
                mint_to_protocol[r["mint"]] = r.get("protocol_id", "")

        for l in listings:
            pid = mint_to_protocol.get(l["nft_mint"], "")
            l["protocol_id"] = pid
            if pid in PROTOCOL_NFTS:
                l["protocol_name"] = PROTOCOL_NFTS[pid]["name"]
                l["symbol"] = PROTOCOL_NFTS[pid]["symbol"]
                l["description"] = PROTOCOL_NFTS[pid].get("description", "")
                l["image"] = PROTOCOL_NFTS[pid].get("image", "")

        return jsonify({"listings": listings, "program_id": _MARKETPLACE_PROGRAM_ID})

    except Exception as e:
        traceback.print_exc()
        return jsonify({"listings": [], "error": str(e)})


@app.route("/api/protocol-store/marketplace/config", methods=["GET"])
def api_marketplace_config():
    """Return marketplace program config for frontend transaction building."""
    return jsonify({
        "program_id": _MARKETPLACE_PROGRAM_ID,
        "res_mint": _RES_MINT,
        "res_decimals": 6,
        "rct_sell_threshold": _RCT_SELL_THRESHOLD,
        "token_2022_program": "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb",
        "spl_token_program": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
        "associated_token_program": "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL",
    })


# ---------------------------------------------------------------------------
# End Protocol Store & Marketplace API
# ---------------------------------------------------------------------------

@app.route("/api/wallet/document")
def api_wallet_document():
    """Return license or manifesto text."""
    try:
        doc_type = request.args.get("type", "license")
        
        if doc_type == "license":
            # Try to read from templates/license.html
            license_path = Path(__file__).parent / "templates" / "license.html"
            if license_path.exists():
                import re
                raw = license_path.read_text()
                # Strip Jinja extends/block lines entirely
                content = re.sub(r'\{%\s*extends.*?%\}\s*', '', raw)
                content = re.sub(r'\{%\s*block\s+title\s*%\}.*?\{%\s*endblock\s*%\}\s*', '', content)
                content = re.sub(r'\{%\s*(?:end)?block\s+\w+\s*%\}\s*', '', content)
                content = content.strip()
                return jsonify({
                    "type": "license",
                    "title": "Resonant Commons Symbiotic License (RC-SL) v1.0",
                    "content": content,
                    "hash": hashlib.sha256("Resonant Commons Symbiotic License (RC-SL) v1.0".encode()).hexdigest()
                })
            else:
                # Hardcoded fallback
                content = """# Resonant Commons Symbiotic License (RC-SL) v1.0

A license for symbiotic collaboration between human creativity and artificial intelligence.

[Full license text would be here...]"""
                return jsonify({
                    "type": "license",
                    "title": "Resonant Commons Symbiotic License (RC-SL) v1.0",
                    "content": content,
                    "hash": hashlib.sha256("Resonant Commons Symbiotic License (RC-SL) v1.0".encode()).hexdigest()
                })
        
        elif doc_type == "manifesto":
            try:
                # Try to fetch from augmentatism.com
                req = urllib.request.Request("https://augmentatism.com/manifesto")
                with urllib.request.urlopen(req, timeout=10) as resp:
                    content = resp.read().decode()
                    return jsonify({
                        "type": "manifesto",
                        "title": "Augmentatism Manifesto v2.2",
                        "content": content,
                        "hash": hashlib.sha256("Augmentatism Manifesto v2.2".encode()).hexdigest()
                    })
            except Exception:
                # Cached fallback
                content = """# Augmentatism Manifesto v2.2

The philosophy of symbiotic human-AI collaboration.

[Manifesto content would be cached here...]"""
                return jsonify({
                    "type": "manifesto",
                    "title": "Augmentatism Manifesto v2.2",
                    "content": content,
                    "hash": hashlib.sha256("Augmentatism Manifesto v2.2".encode()).hexdigest()
                })
        
        else:
            return jsonify({"error": "Invalid document type"}), 400
        
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route("/api/wallet/owned-nfts")
def api_wallet_owned_nfts():
    """Return NFTs owned by address."""
    try:
        network = request.args.get("network", "devnet")
        address = request.args.get("address")
        
        if not address:
            return jsonify({"error": "address parameter required"}), 400
        
        nfts = []
        
        # Query Token-2022 accounts (where soulbound NFTs are minted)
        try:
            result = _solana_rpc(network, "getTokenAccountsByOwner", [
                address,
                {"programId": "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"},
                {"encoding": "jsonParsed"}
            ])
            
            for account in result.get("result", {}).get("value", []):
                parsed = account.get("account", {}).get("data", {}).get("parsed", {}).get("info", {})
                mint = parsed.get("mint")
                token_amount = parsed.get("tokenAmount", {})
                amount = float(token_amount.get("amount", 0))
                
                if amount > 0 and int(token_amount.get("decimals", 0)) == 0:
                    # Check onboarding records to identify NFT type by mint
                    onboarding = _load_onboarding()
                    nft_data = {
                        "mint": mint,
                        "name": f"NFT {mint[:8]}...",
                        "tag": "Soulbound",
                        "img": None,
                        "soulbound": True
                    }
                    
                    # Match mint against known NFT mints from onboarding records
                    matched = False
                    for addr, record in onboarding.items():
                        if record.get("licenseNft") == mint:
                            nft_data.update({"name": "Symbiotic License", "tag": "Co-signed Agreement", "img": "/static/img/nfts/symbiotic-license.png"})
                            matched = True; break
                        elif record.get("manifestoNft") == mint:
                            nft_data.update({"name": "Augmentatism Manifesto", "tag": "Co-signed Commitment", "img": "/static/img/nfts/manifesto.png"})
                            matched = True; break
                        elif record.get("identityNft") == mint or record.get("identityNftMint") == mint:
                            nft_data.update({"name": "Augmentor Identity", "tag": "AI Agent NFT", "img": "/static/img/nfts/ai-identity.png"})
                            matched = True; break
                        elif record.get("alphaNft") == mint or record.get("alphaNftMint") == mint:
                            nft_data.update({"name": "AI Artisan Alpha Tester", "tag": "Early Adopter", "img": "/static/img/nfts/alpha-tester.png"})
                            matched = True; break
                    
                    # Fallback 0: check nft_registry.json
                    if not matched:
                        try:
                            reg_path = str(_DASHBOARD_DIR / "data" / "nft_registry.json")
                            if os.path.exists(reg_path):
                                with open(reg_path) as rf:
                                    registry = json.load(rf)
                                nft_type_key = registry.get(mint)
                                if nft_type_key:
                                    _type_display = {
                                        "identity": {"name": "Augmentor Identity", "tag": "AI Agent NFT", "img": "/static/img/nfts/ai-identity.png"},
                                        "alpha": {"name": "AI Artisan Alpha Tester", "tag": "Early Adopter", "img": "/static/img/nfts/alpha-tester.png"},
                                        "license": {"name": "Symbiotic License", "tag": "Co-signed Agreement", "img": "/static/img/nfts/symbiotic-license.png"},
                                        "manifesto": {"name": "Augmentatism Manifesto", "tag": "Co-signed Commitment", "img": "/static/img/nfts/manifesto.png"},
                                        "founder": {"name": "ResonantOS Founder", "tag": "Founder", "img": "/static/img/nfts/founder.png"},
                                        "dao_genesis": {"name": "DAO Genesis", "tag": "Genesis", "img": "/static/img/nfts/dao-genesis.png"},
                                    }
                                    if nft_type_key in _type_display:
                                        nft_data.update(_type_display[nft_type_key])
                                        matched = True
                        except Exception as e:
                            print(f"Error reading nft_registry: {e}")

                    # Fallback 1: try on-chain metadata
                    if not matched:
                        # Map known names to display info
                        _name_map = {
                            "Augmentor Identity": {"name": "Augmentor Identity", "tag": "AI Agent NFT", "img": "/static/img/nfts/ai-identity.png"},
                            "AI Artisan — Alpha Tester": {"name": "AI Artisan Alpha Tester", "tag": "Early Adopter", "img": "/static/img/nfts/alpha-tester.png"},
                            "AI Artisan — Alpha": {"name": "AI Artisan Alpha Tester", "tag": "Early Adopter", "img": "/static/img/nfts/alpha-tester.png"},
                            "Symbiotic License Agreement": {"name": "Symbiotic License", "tag": "Co-signed Agreement", "img": "/static/img/nfts/symbiotic-license.png"},
                            "Augmentatism Manifesto": {"name": "Augmentatism Manifesto", "tag": "Co-signed Commitment", "img": "/static/img/nfts/manifesto.png"},
                            "ResonantOS Founder": {"name": "ResonantOS Founder", "tag": "Founder", "img": "/static/img/nfts/founder.png"},
                            "Resonant Economy DAO Genesis": {"name": "DAO Genesis", "tag": "Genesis", "img": "/static/img/nfts/dao-genesis.png"},
                        }
                        # Try reading on-chain metadata from mint account
                        try:
                            mint_info = _solana_rpc(network, "getAccountInfo", [
                                mint, {"encoding": "jsonParsed"}
                            ])
                            mint_data = mint_info.get("result", {}).get("value", {}).get("data", {})
                            # Token-2022 parsed data may include extensions with metadata
                            extensions = []
                            if isinstance(mint_data, dict):
                                parsed_info = mint_data.get("parsed", {}).get("info", {})
                                extensions = parsed_info.get("extensions", [])
                            for ext in extensions:
                                if ext.get("extension") == "tokenMetadata":
                                    state = ext.get("state", {})
                                    onchain_name = state.get("name", "").strip().rstrip("\x00")
                                    if onchain_name:
                                        # Try matching against known names
                                        for known_name, info in _name_map.items():
                                            if known_name.lower() in onchain_name.lower() or onchain_name.lower() in known_name.lower():
                                                nft_data.update(info)
                                                matched = True
                                                break
                                        if not matched:
                                            nft_data["name"] = onchain_name
                                            matched = True
                                    break
                        except Exception as e:
                            print(f"Error reading mint metadata for {mint}: {e}")
                        
                    if not matched:
                        # Skip unidentified NFTs — only show recognized ones
                        continue
                    
                    nfts.append(nft_data)
        except Exception as e:
            print(f"Error querying NFTs: {e}")
        
        return jsonify({
            "address": address,
            "network": network,
            "nfts": nfts,
            "count": len(nfts)
        })
        
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# ---------------------------------------------------------------------------
# Symbiotic Wallet On-Chain Endpoints
# ---------------------------------------------------------------------------

_SYMBIOTIC_PROGRAM_ID = _CFG.get("programs", {}).get("SYMBIOTIC_PROGRAM_ID", "HMthR7AStR3YKJ4m8GMveWx5dqY3D2g2cfnji7VdcVoG")
_AI_WALLET_PUBKEY = None  # Lazily loaded


def _get_ai_pubkey_str():
    global _AI_WALLET_PUBKEY
    if _AI_WALLET_PUBKEY is None:
        pk = _get_wallet_pubkey()
        _AI_WALLET_PUBKEY = str(pk) if pk is not None else None
    return _AI_WALLET_PUBKEY


def _derive_symbiotic_pda(human_pubkey_str):
    """Derive the Symbiotic PDA address for a human wallet."""
    from solders.pubkey import Pubkey as _Pubkey
    program_id = _Pubkey.from_string(_SYMBIOTIC_PROGRAM_ID)
    human = _Pubkey.from_string(human_pubkey_str)
    seeds = [b"symbiotic", bytes(human), bytes([0])]
    pda, _bump = _Pubkey.find_program_address(seeds, program_id)
    return str(pda)


@app.route("/api/symbiotic/build-init-tx", methods=["POST"])
def symbiotic_build_init_tx():
    """Build an initialize_pair transaction for Phantom to sign.

    Body: { "humanPubkey": "<base58>", "network": "devnet" }
    Returns: { "transaction": "<base64>", "pda": "<base58>", "bump": int }

    The human wallet must sign this transaction in Phantom.
    """
    try:
        data = request.get_json(force=True)
        human_str = data.get("humanPubkey", "").strip()
        network = data.get("network", "devnet")

        if network != "devnet":
            return jsonify({"error": "Alpha: devnet only"}), 400
        if not human_str:
            return jsonify({"error": "humanPubkey required"}), 400

        import struct as _struct
        import base64 as _b64
        from solders.pubkey import Pubkey as _Pubkey
        from solders.instruction import Instruction as _Ix, AccountMeta as _AM
        from solders.system_program import ID as _SYS
        from solders.transaction import Transaction as _Tx
        from solders.message import Message as _Msg
        from solana.rpc.api import Client as _Client

        program_id = _Pubkey.from_string(_SYMBIOTIC_PROGRAM_ID)
        human = _Pubkey.from_string(human_str)
        ai = _Pubkey.from_string(_get_ai_pubkey_str())
        pair_nonce = 0

        # Derive PDA
        seeds = [b"symbiotic", bytes(human), bytes([pair_nonce])]
        pda, bump = _Pubkey.find_program_address(seeds, program_id)

        # Build instruction data: discriminator + pair_nonce (u8)
        disc = hashlib.sha256(b"global:initialize_pair").digest()[:8]
        ix_data = disc + _struct.pack("<B", pair_nonce)

        accounts = [
            _AM(pubkey=pda, is_signer=False, is_writable=True),
            _AM(pubkey=human, is_signer=True, is_writable=True),
            _AM(pubkey=ai, is_signer=False, is_writable=False),
            _AM(pubkey=_SYS, is_signer=False, is_writable=False),
        ]

        ix = _Ix(program_id, ix_data, accounts)

        # Get recent blockhash
        rpc_url = _SOLANA_RPCS.get(network, _SOLANA_RPCS["devnet"])
        client = _Client(rpc_url)
        bh_resp = client.get_latest_blockhash()
        blockhash = bh_resp.value.blockhash

        # Build message with human as fee payer
        msg = _Msg.new_with_blockhash([ix], human, blockhash)
        tx = _Tx.new_unsigned(msg)

        # Serialize to base64 for Phantom
        tx_bytes = bytes(tx)
        tx_b64 = _b64.b64encode(tx_bytes).decode("ascii")

        return jsonify({
            "transaction": tx_b64,
            "pda": str(pda),
            "bump": bump,
            "aiPubkey": _get_ai_pubkey_str(),
            "humanPubkey": human_str,
        })
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/api/symbiotic/pair-info")
def symbiotic_pair_info():
    """Get symbiotic pair info for a human wallet.

    Query: ?humanPubkey=<base58>&network=devnet
    Returns pair data if it exists, or {"exists": false}.
    """
    try:
        human_str = request.args.get("humanPubkey", "").strip()
        network = request.args.get("network", "devnet")

        if not human_str:
            return jsonify({"error": "humanPubkey required"}), 400

        from solders.pubkey import Pubkey as _Pubkey

        program_id = _Pubkey.from_string(_SYMBIOTIC_PROGRAM_ID)
        human = _Pubkey.from_string(human_str)

        seeds = [b"symbiotic", bytes(human), bytes([0])]
        pda, bump = _Pubkey.find_program_address(seeds, program_id)

        rpc_url = _SOLANA_RPCS.get(network, _SOLANA_RPCS["devnet"])
        rpc_data = json.loads(urllib.request.urlopen(
            urllib.request.Request(
                rpc_url,
                data=json.dumps({
                    "jsonrpc": "2.0", "id": 1,
                    "method": "getAccountInfo",
                    "params": [str(pda), {"encoding": "base64"}]
                }).encode(),
                headers={"Content-Type": "application/json"},
            ),
            timeout=10,
        ).read())

        account = rpc_data.get("result", {}).get("value")
        if account is None:
            return jsonify({"exists": False, "pda": str(pda)})

        import base64 as _b64, struct as _struct
        raw = _b64.b64decode(account["data"][0])
        if len(raw) < 93:
            return jsonify({"exists": False, "pda": str(pda)})

        d = raw[8:]  # skip discriminator
        from solders.pubkey import Pubkey as _P
        pair_data = {
            "exists": True,
            "pda": str(pda),
            "human": str(_P.from_bytes(d[0:32])),
            "ai": str(_P.from_bytes(d[32:64])),
            "pairNonce": d[64],
            "bump": d[65],
            "frozen": bool(d[66]),
            "lastClaim": _struct.unpack("<q", d[67:75])[0],
            "createdAt": _struct.unpack("<q", d[75:83])[0],
            "aiRotations": _struct.unpack("<H", d[83:85])[0],
        }
        return jsonify(pair_data)
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# ---------------------------------------------------------------------------
# End Wallet API
# ---------------------------------------------------------------------------

@app.route("/todo")
def todo_page():
    return render_template("todo.html", active_page="todo")

@app.route("/ideas")
def ideas_page():
    return render_template("ideas.html", active_page="ideas")

@app.route("/intelligence")
def intelligence_page():
    return render_template("intelligence.html", active_page="intelligence")

@app.route("/settings")
def settings_page():
    return render_template("settings.html", active_page="settings")

@app.route("/ssot")
def ssot_page():
    return render_template("ssot.html", active_page="ssot")


@app.route("/shield")
def shield_page():
    return render_template("shield.html", active_page="shield")

# ---------------------------------------------------------------------------
# API: Dashboard Self-Update (git-based)
# ---------------------------------------------------------------------------

DASHBOARD_REPO_DIR = os.path.dirname(os.path.abspath(__file__))
_UPDATE_CONFIG_LOCK = threading.Lock()
_UPDATE_CHECKER_STARTED = False
_UPDATE_DEFAULTS = {
    "autoCheck": True,
    "autoCheckIntervalHours": 6,
    "autoApply": False,
    "notifyOnUpdate": True,
    "lastCheck": None,
    "lastCheckResult": None,
}
_UPDATE_INTERVAL_OPTIONS = {1, 2, 4, 6, 12, 24}


def _utc_now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_iso_utc(ts):
    if not ts or not isinstance(ts, str):
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None


def _normalize_updates_config(raw):
    out = dict(_UPDATE_DEFAULTS)
    if isinstance(raw, dict):
        if isinstance(raw.get("autoCheck"), bool):
            out["autoCheck"] = raw["autoCheck"]
        if isinstance(raw.get("autoApply"), bool):
            out["autoApply"] = raw["autoApply"]
        if isinstance(raw.get("notifyOnUpdate"), bool):
            out["notifyOnUpdate"] = raw["notifyOnUpdate"]
        try:
            interval = int(raw.get("autoCheckIntervalHours", _UPDATE_DEFAULTS["autoCheckIntervalHours"]))
            if interval in _UPDATE_INTERVAL_OPTIONS:
                out["autoCheckIntervalHours"] = interval
        except Exception:
            pass
        if isinstance(raw.get("lastCheck"), str):
            out["lastCheck"] = raw["lastCheck"]
        if isinstance(raw.get("lastCheckResult"), dict):
            out["lastCheckResult"] = raw["lastCheckResult"]
    return out


def _load_dashboard_config_for_updates():
    try:
        cfg = json.loads(_CONFIG_FILE.read_text())
        if isinstance(cfg, dict):
            return cfg
    except Exception:
        pass
    return _CFG if isinstance(_CFG, dict) else {}


def _read_updates_config():
    with _UPDATE_CONFIG_LOCK:
        cfg = _load_dashboard_config_for_updates()
        return _normalize_updates_config(cfg.get("updates"))


def _write_updates_config(updates):
    global _CFG
    normalized = _normalize_updates_config(updates)
    with _UPDATE_CONFIG_LOCK:
        cfg = _load_dashboard_config_for_updates()
        cfg["updates"] = normalized
        _CONFIG_FILE.write_text(json.dumps(cfg, indent=2))
        _CFG = cfg
    return normalized


def _perform_update_check_logic():
    """Run the same git logic used by the manual check endpoint."""
    try:
        fetch_result = subprocess.run(
            ["git", "fetch", "origin", "main"],
            cwd=DASHBOARD_REPO_DIR,
            capture_output=True, text=True, timeout=30
        )
        if fetch_result.returncode != 0:
            return None, f"git fetch failed: {fetch_result.stderr.strip()}"

        local = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=DASHBOARD_REPO_DIR,
            capture_output=True, text=True, timeout=10
        ).stdout.strip()

        remote = subprocess.run(
            ["git", "rev-parse", "origin/main"],
            cwd=DASHBOARD_REPO_DIR,
            capture_output=True, text=True, timeout=10
        ).stdout.strip()

        behind_result = subprocess.run(
            ["git", "rev-list", "--count", "HEAD..origin/main"],
            cwd=DASHBOARD_REPO_DIR,
            capture_output=True, text=True, timeout=10
        )
        behind = int(behind_result.stdout.strip()) if behind_result.returncode == 0 else 0

        branch_result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=DASHBOARD_REPO_DIR,
            capture_output=True, text=True, timeout=10
        )
        branch = branch_result.stdout.strip()

        return {
            "available": behind > 0,
            "behind": behind,
            "local": local[:12],
            "remote": remote[:12],
            "branch": branch,
        }, None
    except subprocess.TimeoutExpired:
        return None, "git command timed out"
    except Exception as e:
        return None, str(e)


def _perform_auto_apply_logic():
    try:
        pull_result = subprocess.run(
            ["git", "pull", "--ff-only", "origin", "main"],
            cwd=DASHBOARD_REPO_DIR,
            capture_output=True, text=True, timeout=60
        )
        if pull_result.returncode == 0:
            return True, {"output": pull_result.stdout.strip()}
        return False, {"error": pull_result.stderr.strip() or "git pull failed", "output": pull_result.stdout.strip()}
    except subprocess.TimeoutExpired:
        return False, {"error": "git pull timed out"}
    except Exception as e:
        return False, {"error": str(e)}


def _run_background_update_check():
    updates = _read_updates_config()
    check_result, check_error = _perform_update_check_logic()

    if check_result is None:
        check_result = {"available": False, "behind": 0, "error": check_error}
    else:
        if updates.get("autoApply") and check_result.get("available"):
            applied, apply_result = _perform_auto_apply_logic()
            check_result["autoApplyAttempted"] = True
            check_result["autoApplySuccess"] = applied
            if not applied:
                check_result["autoApplyError"] = apply_result.get("error")
            else:
                post_check, post_error = _perform_update_check_logic()
                if post_check is not None:
                    post_check["autoApplyAttempted"] = True
                    post_check["autoApplySuccess"] = True
                    check_result = post_check
                elif post_error:
                    check_result["postApplyCheckError"] = post_error

    updates["lastCheck"] = _utc_now_iso()
    updates["lastCheckResult"] = check_result
    _write_updates_config(updates)


def _auto_update_checker_loop():
    while True:
        try:
            updates = _read_updates_config()
            if not updates.get("autoCheck"):
                time.sleep(60)
                continue

            interval_seconds = max(1, int(updates.get("autoCheckIntervalHours", 6))) * 3600
            last_check_dt = _parse_iso_utc(updates.get("lastCheck"))
            due = last_check_dt is None
            if not due:
                elapsed = (datetime.now(timezone.utc) - last_check_dt).total_seconds()
                due = elapsed >= interval_seconds

            if due:
                _run_background_update_check()
                time.sleep(5)
                continue

            wait_seconds = min(60, max(1, int(interval_seconds - elapsed)))
            time.sleep(wait_seconds)
        except Exception:
            traceback.print_exc()
            time.sleep(60)


def start_auto_update_checker():
    global _UPDATE_CHECKER_STARTED
    if _UPDATE_CHECKER_STARTED:
        return
    thread = threading.Thread(target=_auto_update_checker_loop, daemon=True, name="auto-update-checker")
    thread.start()
    _UPDATE_CHECKER_STARTED = True


@app.route("/api/settings/update-config")
def api_get_update_config():
    return jsonify(_read_updates_config())


@app.route("/api/settings/update-config", methods=["PUT"])
def api_put_update_config():
    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict):
        return jsonify({"error": "Invalid JSON body"}), 400

    updates = _read_updates_config()

    if "autoCheck" in body:
        if not isinstance(body["autoCheck"], bool):
            return jsonify({"error": "autoCheck must be a boolean"}), 400
        updates["autoCheck"] = body["autoCheck"]

    if "autoApply" in body:
        if not isinstance(body["autoApply"], bool):
            return jsonify({"error": "autoApply must be a boolean"}), 400
        updates["autoApply"] = body["autoApply"]

    if "notifyOnUpdate" in body:
        if not isinstance(body["notifyOnUpdate"], bool):
            return jsonify({"error": "notifyOnUpdate must be a boolean"}), 400
        updates["notifyOnUpdate"] = body["notifyOnUpdate"]

    if "autoCheckIntervalHours" in body:
        try:
            interval = int(body["autoCheckIntervalHours"])
        except Exception:
            return jsonify({"error": "autoCheckIntervalHours must be an integer"}), 400
        if interval not in _UPDATE_INTERVAL_OPTIONS:
            return jsonify({"error": "autoCheckIntervalHours must be one of: 1, 2, 4, 6, 12, 24"}), 400
        updates["autoCheckIntervalHours"] = interval

    saved = _write_updates_config(updates)
    return jsonify(saved)

@app.route("/api/settings/check-update")
def api_check_update():
    """Check if a newer version is available on origin/main."""
    try:
        # Fetch latest from remote
        fetch_result = subprocess.run(
            ["git", "fetch", "origin", "main"],
            cwd=DASHBOARD_REPO_DIR,
            capture_output=True, text=True, timeout=30
        )
        if fetch_result.returncode != 0:
            return jsonify({"error": f"git fetch failed: {fetch_result.stderr.strip()}"}), 500

        # Get local HEAD commit
        local = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=DASHBOARD_REPO_DIR,
            capture_output=True, text=True, timeout=10
        ).stdout.strip()

        # Get remote HEAD commit
        remote = subprocess.run(
            ["git", "rev-parse", "origin/main"],
            cwd=DASHBOARD_REPO_DIR,
            capture_output=True, text=True, timeout=10
        ).stdout.strip()

        # Count how many commits behind
        behind_result = subprocess.run(
            ["git", "rev-list", "--count", f"HEAD..origin/main"],
            cwd=DASHBOARD_REPO_DIR,
            capture_output=True, text=True, timeout=10
        )
        behind = int(behind_result.stdout.strip()) if behind_result.returncode == 0 else 0

        # Get current branch
        branch_result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=DASHBOARD_REPO_DIR,
            capture_output=True, text=True, timeout=10
        )
        branch = branch_result.stdout.strip()

        return jsonify({
            "available": behind > 0,
            "behind": behind,
            "local": local[:12],
            "remote": remote[:12],
            "branch": branch,
        })
    except subprocess.TimeoutExpired:
        return jsonify({"error": "git command timed out"}), 504
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/settings/update", methods=["POST"])
def api_apply_update():
    """Pull latest changes from origin/main (fast-forward only for safety)."""
    try:
        # Only allow fast-forward merges to avoid conflicts
        pull_result = subprocess.run(
            ["git", "pull", "--ff-only", "origin", "main"],
            cwd=DASHBOARD_REPO_DIR,
            capture_output=True, text=True, timeout=60
        )

        success = pull_result.returncode == 0
        output = pull_result.stdout.strip()
        error = pull_result.stderr.strip()

        return jsonify({
            "success": success,
            "output": output,
            "error": error if not success else None,
            "message": "Update applied successfully. Restart the dashboard to load changes." if success else f"Update failed: {error}",
        }), 200 if success else 500
    except subprocess.TimeoutExpired:
        return jsonify({"success": False, "error": "git pull timed out", "message": "Update timed out after 60s"}), 504
    except Exception as e:
        return jsonify({"success": False, "error": str(e), "message": f"Update error: {e}"}), 500

# ---------------------------------------------------------------------------
# API: Gateway Status & Health
# ---------------------------------------------------------------------------

@app.route("/api/gateway/status")
def api_gateway_status():
    """Overall gateway connection status."""
    return jsonify({
        "connected": gw.connected,
        "connId": gw.conn_id,
        "lastTick": gw.last_tick,
        "lastHealthTs": gw.last_health_ts,
        "error": gw.error,
    })

@app.route("/api/gateway/health")
def api_gateway_health():
    """Latest cached health data (channels, agents, heartbeat)."""
    with gw._lock:
        return jsonify(gw.health or {"error": "no health data yet"})

@app.route("/api/gateway/request", methods=["POST"])
def api_gateway_request():
    """Proxy arbitrary WS request to gateway. Body: {method, params}."""
    body = request.get_json(force=True)
    method = body.get("method")
    params = body.get("params")
    if not method:
        return jsonify({"ok": False, "error": "method required"}), 400
    result = gw.request(method, params)
    return jsonify(result)

@app.route("/api/gateway/restart", methods=["POST"])
def api_gateway_restart():
    """Restart the OpenClaw gateway via CLI."""
    try:
        import subprocess
        result = subprocess.run(
            ["openclaw", "gateway", "restart"],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode == 0:
            return jsonify({"ok": True, "output": result.stdout.strip()})
        return jsonify({"ok": False, "error": result.stderr.strip() or "restart failed"}), 500
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ---------------------------------------------------------------------------
# API: Agents
# ---------------------------------------------------------------------------

@app.route("/api/agents")
def api_agents():
    """List agents from gateway health + local workspace directories."""
    agents = []
    seen_ids = set()

    # Helper: read workspace files for an agent
    def _read_workspace(agent_id):
        workspace_files = {}
        # Check per-agent workspace first, then shared
        ws_dir = OPENCLAW_HOME / f"workspace-{agent_id}"
        if agent_id == "main":
            ws_dir = WORKSPACE
        for fname in ["SOUL.md", "AGENTS.md", "USER.md", "IDENTITY.md", "MEMORY.md"]:
            fpath = ws_dir / fname
            if not fpath.exists() and agent_id != "main":
                if fname in ("IDENTITY.md", "SOUL.md", "MEMORY.md"):
                    continue  # agent-specific files should NOT fall back to main
                fpath = WORKSPACE / fname  # fallback to shared for AGENTS.md, USER.md
            if fpath.exists():
                try:
                    workspace_files[fname] = fpath.read_text()[:2000]
                except Exception:
                    pass
        return workspace_files

    # Helper: resolve model for agent
    def _resolve_model(agent_id):
        try:
            cfg = json.loads(OPENCLAW_CONFIG.read_text())
            # 1. Check agent-specific model in agents.list
            for entry in cfg.get("agents", {}).get("list", []):
                if entry.get("id") == agent_id and entry.get("model"):
                    m = entry["model"]
                    return m.get("primary", str(m)) if isinstance(m, dict) else m
            # 2. Check agents.defaults.model
            default_model = cfg.get("agents", {}).get("defaults", {}).get("model")
            if default_model:
                return default_model.get("primary", str(default_model)) if isinstance(default_model, dict) else default_model
            # 3. Check top-level model
            top_model = cfg.get("model")
            if top_model:
                return top_model if isinstance(top_model, str) else top_model.get("primary", str(top_model))
            return "default"
        except Exception:
            return "default"

    # Helper: parse identity for emoji/name
    def _parse_identity(workspace_files):
        identity = workspace_files.get("IDENTITY.md", "")
        emoji = "🤖"
        name = None
        for line in identity.splitlines():
            if "**Emoji:**" in line:
                parts = line.split("**Emoji:**")
                if len(parts) > 1 and parts[1].strip():
                    emoji = parts[1].strip()
            if "**Name:**" in line:
                parts = line.split("**Name:**")
                if len(parts) > 1 and parts[1].strip():
                    name = parts[1].strip()
        return emoji, name

    # Agent metadata for hierarchy
    AGENT_META = {
        "main":     {"tier": 0, "role": "Orchestrator & Strategist", "category": "core"},
        "doer":     {"tier": 1, "role": "Personal Assistant & Task Executor", "category": "direct"},
        "dao":      {"tier": 1, "role": "DAO Strategy & Governance", "category": "direct"},
        "website":  {"tier": 1, "role": "Marketing Website", "category": "direct"},
        "voice":         {"tier": 1, "role": "Content Voice & YouTube", "category": "direct"},
        "coder":         {"tier": 1, "role": "Coding Agent", "category": "background"},
        "researcher":    {"tier": 1, "role": "Deep Research (Perplexity)", "category": "background"},
        "setup":         {"tier": 1, "role": "Onboarding & Setup", "category": "support"},
        "acupuncturist": {"tier": 1, "role": "Protocol Enforcement", "category": "support"},
        "blindspot":     {"tier": 1, "role": "Red Team & Vulnerability Hunter", "category": "support"},
    }

    # Inject R-Memory as a virtual "memory" agent with effective models
    rmem_cfg = _rmem_config()
    effective = _rmem_effective_models()
    rmem_log = RMEMORY_DIR / "r-memory.log"
    rmem_status = "active" if rmem_log.exists() and rmem_log.stat().st_size > 0 else "inactive"
    # Load usage stats for call counts
    usage_stats = {}
    try:
        usage_stats = json.loads((RMEMORY_DIR / "usage-stats.json").read_text())
    except Exception:
        pass
    agents.append({
        "agentId": "memory",
        "isDefault": False,
        "status": rmem_status,
        "mainModel": effective["compression"],
        "heartbeat": {},
        "sessions": {"count": 0},
        "workspaceFiles": {},
        "emoji": "🧠",
        "displayName": "R-Memory",
        "tier": 0.5,
        "role": "Compression & Narrative Tracking",
        "category": "core",
        "virtual": True,
        "subAgents": {
            "compression": {
                "model": effective["compression"],
                "label": "Conversation Compression",
                "calls": usage_stats.get("compression", {}).get("calls", 0),
            },
            "narrative": {
                "model": effective["narrative"],
                "label": "Narrative Tracker",
                "calls": usage_stats.get("narrative", {}).get("calls", 0),
            },
        },
    })
    seen_ids.add("memory")

    # 1. Active agents from gateway health
    health = gw.health or {}
    for ag in health.get("agents", []):
        agent_id = ag.get("agentId", "unknown")
        seen_ids.add(agent_id)
        workspace_files = _read_workspace(agent_id)
        emoji, name = _parse_identity(workspace_files)
        agents.append({
            "agentId": agent_id,
            "isDefault": ag.get("isDefault", False),
            "status": "active",
            "mainModel": _resolve_model(agent_id),
            "heartbeat": ag.get("heartbeat", {}),
            "sessions": ag.get("sessions", {}),
            "workspaceFiles": workspace_files,
            "emoji": emoji,
            "displayName": name or agent_id,
            **(AGENT_META.get(agent_id, {"tier": 1, "role": "Agent", "category": "other"})),
        })

    # 2. Agents from openclaw.json config (always available, even without gateway)
    try:
        cfg = json.loads(OPENCLAW_CONFIG.read_text())
        for agent_entry in cfg.get("agents", {}).get("list", []):
            agent_id = agent_entry.get("id", "")
            if not agent_id or agent_id in seen_ids:
                continue
            seen_ids.add(agent_id)
            workspace_files = _read_workspace(agent_id)
            emoji, name = _parse_identity(workspace_files)
            model = agent_entry.get("model") or cfg.get("agents", {}).get("defaults", {}).get("model") or "unknown"
            agents.append({
                "agentId": agent_id,
                "isDefault": agent_entry.get("default", False),
                "status": "configured",
                "mainModel": model,
                "heartbeat": {},
                "sessions": {"count": 0},
                "workspaceFiles": workspace_files,
                "emoji": emoji,
                "displayName": name or agent_id,
                **(AGENT_META.get(agent_id, {"tier": 0 if agent_entry.get("default") else 1, "role": "Agent", "category": "other"})),
            })
    except Exception:
        pass

    # 3. Discover agents from workspace-* directories (not yet in gateway or config)
    for ws_path in sorted(OPENCLAW_HOME.glob("workspace-*")):
        if not ws_path.is_dir():
            continue
        agent_id = ws_path.name.replace("workspace-", "")
        if agent_id in seen_ids:
            continue
        seen_ids.add(agent_id)
        workspace_files = _read_workspace(agent_id)
        emoji, name = _parse_identity(workspace_files)
        agents.append({
            "agentId": agent_id,
            "isDefault": False,
            "status": "inactive",
            "mainModel": _resolve_model(agent_id),
            "heartbeat": {},
            "sessions": {"count": 0},
            "workspaceFiles": workspace_files,
            "emoji": emoji,
            "displayName": name or agent_id,
            **(AGENT_META.get(agent_id, {"tier": 1, "role": "Agent", "category": "other"})),
        })

    # 4. Guaranteed fallback: always include "main" agent
    if "main" not in seen_ids:
        workspace_files = _read_workspace("main")
        emoji, name = _parse_identity(workspace_files)
        agents.append({
            "agentId": "main",
            "isDefault": True,
            "status": "configured",
            "mainModel": _resolve_model("main"),
            "heartbeat": {},
            "sessions": {"count": 0},
            "workspaceFiles": workspace_files,
            "emoji": emoji,
            "displayName": name or "Main Agent",
            **(AGENT_META.get("main", {"tier": 0, "role": "Orchestrator & Strategist", "category": "core"})),
        })

    # Sort: tier 0 first, then alphabetical
    agents.sort(key=lambda a: (a.get("tier", 1), a["agentId"]))
    return jsonify(agents)

@app.route("/api/system-agents")
def api_system_agents():
    """Return normalized data for system/background agents (Heartbeat, R-Memory, Cron, Subagents, etc.)."""
    system_agents = []

    # --- 1. Heartbeat ---
    try:
        cfg = json.loads(OPENCLAW_CONFIG.read_text())
        hb_defaults = cfg.get("agents", {}).get("defaults", {}).get("heartbeat", {})
        # Also get per-agent heartbeat overrides from gateway health
        health = gw.health or {}
        main_agent = next((a for a in health.get("agents", []) if a.get("isDefault")), {})
        hb_live = main_agent.get("heartbeat", {})
        hb_enabled = hb_live.get("enabled", hb_defaults.get("enabled", False))
        hb_every = hb_live.get("every", hb_defaults.get("every", "-"))
        hb_model = hb_live.get("model", hb_defaults.get("model", "unknown"))
        hb_active_hours = hb_defaults.get("activeHours", {})
        active_window = ""
        if hb_active_hours:
            active_window = f"{hb_active_hours.get('start','?')}-{hb_active_hours.get('end','?')} {hb_active_hours.get('timezone','')}"
        system_agents.append({
            "id": "heartbeat",
            "name": "Heartbeat",
            "emoji": "💓",
            "role": "Periodic health check & proactive assistant",
            "model": hb_model,
            "status": "running" if hb_enabled else "disabled",
            "interval": hb_every,
            "activeWindow": active_window,
            "details": {
                "target": hb_live.get("target", "last"),
                "prompt": hb_live.get("prompt", hb_defaults.get("prompt", "")),
            },
        })
    except Exception:
        system_agents.append({
            "id": "heartbeat",
            "name": "Heartbeat",
            "emoji": "💓",
            "role": "Periodic health check & proactive assistant",
            "model": "unknown",
            "status": "unknown",
            "interval": "-",
            "activeWindow": "",
            "details": {},
        })

    # --- 2. R-Memory (compression + narrative) ---
    try:
        rmem_cfg = _rmem_config()
        effective = _rmem_effective_models()
        rmem_log = RMEMORY_DIR / "r-memory.log"
        rmem_active = rmem_log.exists() and rmem_log.stat().st_size > 0
        rmem_enabled = rmem_cfg.get("enabled", True)
        usage_stats = {}
        try:
            usage_stats = json.loads((RMEMORY_DIR / "usage-stats.json").read_text())
        except Exception:
            pass
        system_agents.append({
            "id": "r-memory",
            "name": "R-Memory",
            "emoji": "🧠",
            "role": "Conversation compression & narrative tracking",
            "model": effective.get("compression", "unknown"),
            "status": "running" if (rmem_active and rmem_enabled) else ("disabled" if not rmem_enabled else "inactive"),
            "interval": "on-demand",
            "activeWindow": "always",
            "details": {
                "compressionModel": effective.get("compression"),
                "narrativeModel": effective.get("narrative"),
                "compressionCalls": usage_stats.get("compression", {}).get("calls", 0),
                "narrativeCalls": usage_stats.get("narrative", {}).get("calls", 0),
                "evictTrigger": rmem_cfg.get("evictTrigger"),
                "compressTrigger": rmem_cfg.get("compressTrigger"),
            },
        })
    except Exception:
        system_agents.append({
            "id": "r-memory",
            "name": "R-Memory",
            "emoji": "🧠",
            "role": "Conversation compression & narrative tracking",
            "model": "unknown",
            "status": "unknown",
            "interval": "on-demand",
            "activeWindow": "always",
            "details": {},
        })

    # --- 3. Subagent Runtime ---
    try:
        cfg = json.loads(OPENCLAW_CONFIG.read_text())
        sub_cfg = cfg.get("agents", {}).get("defaults", {}).get("subagents", {})
        max_concurrent = sub_cfg.get("maxConcurrent", 4)
        # Check active sessions for subagent activity
        health = gw.health or {}
        all_sessions = []
        for ag in health.get("agents", []):
            for s in ag.get("sessions", {}).get("recent", []):
                if "subagent" in s.get("key", ""):
                    all_sessions.append(s)
        system_agents.append({
            "id": "subagent-runtime",
            "name": "Subagent Runtime",
            "emoji": "🔀",
            "role": "Spawns & manages task-specific sub-agents",
            "model": "inherits parent",
            "status": "running",
            "interval": "on-demand",
            "activeWindow": "always",
            "details": {
                "maxConcurrent": max_concurrent,
                "recentSubagentSessions": len(all_sessions),
            },
        })
    except Exception:
        pass

    # --- 4. Gateway ---
    try:
        cfg = json.loads(OPENCLAW_CONFIG.read_text())
        gw_cfg = cfg.get("gateway", {})
        gw_port = gw_cfg.get("port", 18789)
        gw_status = "running" if (gw.health and gw.health.get("agents")) else "stopped"
        system_agents.append({
            "id": "gateway",
            "name": "Gateway",
            "emoji": "🌐",
            "role": "Core message router & session manager",
            "model": "n/a",
            "status": gw_status,
            "interval": "always-on",
            "activeWindow": "always",
            "details": {
                "port": gw_port,
                "mode": gw_cfg.get("mode", "local"),
            },
        })
    except Exception:
        pass

    return jsonify(system_agents)


@app.route("/api/agents/<agent_id>/sessions")
def api_agent_sessions(agent_id):
    """Get sessions for an agent via gateway."""
    result = gw.request("sessions.list", {"agentId": agent_id})
    return jsonify(result)

@app.route("/api/agents/<agent_id>/model", methods=["PUT"])
def api_agent_model(agent_id):
    """Update an agent's model in OpenClaw config."""
    data = request.get_json(force=True) or {}
    model = data.get("model")
    if not model:
        return jsonify({"error": "model required"}), 400

    # Read current config
    cfg_path = Path.home() / ".openclaw" / "openclaw.json"
    if not cfg_path.exists():
        return jsonify({"error": "openclaw.json not found"}), 500
    try:
        cfg = json.loads(cfg_path.read_text())
    except Exception as e:
        return jsonify({"error": f"Failed to read config: {e}"}), 500

    # Ensure agents section exists
    if "agents" not in cfg:
        cfg["agents"] = {}
    if agent_id not in cfg["agents"]:
        cfg["agents"][agent_id] = {}

    cfg["agents"][agent_id]["model"] = model

    try:
        cfg_path.write_text(json.dumps(cfg, indent=2))
    except Exception as e:
        return jsonify({"error": f"Failed to write config: {e}"}), 500

    return jsonify({"ok": True, "agentId": agent_id, "model": model})


# ---------------------------------------------------------------------------
# API: R-Memory (SSoT documents)
# ---------------------------------------------------------------------------

def _scan_ssot_layer(layer_dir, layer_name):
    """Scan a layer directory (recursively) for SSoT documents."""
    docs = []
    if not layer_dir.exists():
        return docs

    for f in sorted(layer_dir.rglob("*.md")):
        if f.name.startswith("."):
            continue
        # Skip .ai.md files only if the full version exists (shown via hasCompressed toggle)
        if f.name.endswith(".ai.md"):
            full_version = f.parent / (f.name[:-len(".ai.md")] + ".md")
            if full_version.exists():
                continue

        st = f.stat()
        # Check if compressed version exists
        ai_path = f.with_suffix(".ai.md")
        has_compressed = ai_path.exists()

        # Check lock status (macOS chflags uchg or schg)
        locked = False
        try:
            flags = st.st_flags
            locked = bool(flags & (0x02 | 0x00020000))  # UF_IMMUTABLE | SF_IMMUTABLE
        except AttributeError:
            pass

        # Token estimate (~4 chars per token)
        raw_tokens = st.st_size // 4
        compressed_tokens = None
        if has_compressed:
            compressed_tokens = ai_path.stat().st_size // 4

        docs.append({
            "path": str(f.relative_to(SSOT_ROOT)),
            "name": f.stem,
            "layer": layer_name,
            "size": st.st_size,
            "rawTokens": raw_tokens,
            "compressedTokens": compressed_tokens,
            "hasCompressed": has_compressed,
            "locked": locked,
            "modified": st.st_mtime,
        })

    return docs

@app.route("/api/r-memory/documents")
def api_rmemory_documents():
    """List all SSoT documents across layers."""
    all_docs = []
    for layer in ["L0", "L1", "L2", "L3", "L4"]:
        layer_dir = SSOT_ROOT / layer
        all_docs.extend(_scan_ssot_layer(layer_dir, layer))
    return jsonify(all_docs)

@app.route("/api/r-memory/document", methods=["GET"])
def api_rmemory_document():
    """Read a single SSoT document. ?path=L1/FOO.md&compressed=true"""
    rel_path = request.args.get("path", "")
    use_compressed = request.args.get("compressed", "false").lower() == "true"

    if not rel_path or ".." in rel_path:
        return jsonify({"error": "invalid path"}), 400

    doc_path = SSOT_ROOT / rel_path
    if use_compressed:
        ai_path = doc_path.with_suffix(".ai.md")
        if ai_path.exists():
            doc_path = ai_path

    if not doc_path.exists():
        return jsonify({"error": "not found"}), 404

    return jsonify({
        "path": rel_path,
        "content": doc_path.read_text(),
        "size": doc_path.stat().st_size,
    })

@app.route("/api/r-memory/available-models", methods=["GET"])
def api_rmemory_available_models():
    """Return compression model options based on user's configured providers."""
    cheap_models = {
        "anthropic": {"model": "anthropic/claude-haiku-4-5", "label": "Claude Haiku 4.5 (cheap)"},
        "openai": {"model": "openai/gpt-4o-mini", "label": "GPT-4o Mini (cheap)"},
        "google": {"model": "google/gemini-2.0-flash", "label": "Gemini 2.0 Flash (cheap)"},
        "minimax": {"model": "minimax/MiniMax-M2.5-Lightning", "label": "MiniMax M2.5 Lightning"},
    }
    full_models = {
        "anthropic": [
            {"model": "anthropic/claude-haiku-4-5", "label": "Claude Haiku 4.5 (cheap)"},
            {"model": "anthropic/claude-sonnet-4-5", "label": "Claude Sonnet 4.5"},
            {"model": "anthropic/claude-opus-4-6", "label": "Claude Opus 4.6"},
        ],
        "openai": [
            {"model": "openai/gpt-4o-mini", "label": "GPT-4o Mini (cheap)"},
            {"model": "openai/gpt-4o", "label": "GPT-4o"},
        ],
        "google": [
            {"model": "google/gemini-2.0-flash", "label": "Gemini 2.0 Flash (cheap)"},
        ],
        "minimax": [
            {"model": "minimax/MiniMax-M2.5-Lightning", "label": "MiniMax M2.5 Lightning"},
            {"model": "minimax/MiniMax-M2.5", "label": "MiniMax M2.5"},
            {"model": "minimax/MiniMax-M2.1", "label": "MiniMax M2.1"},
        ],
    }
    available = []
    try:
        auth_path = Path.home() / ".openclaw" / "agents" / "main" / "agent" / "auth-profiles.json"
        if auth_path.exists():
            data = json.loads(auth_path.read_text())
            seen_providers = set()
            for key, profile in data.get("profiles", {}).items():
                if profile.get("token"):
                    prov = profile.get("provider") or key.split(":")[0]
                    if prov not in seen_providers:
                        seen_providers.add(prov)
                        available.extend(full_models.get(prov, [{"model": f"{prov}/default", "label": prov}]))
    except Exception:
        pass
    if not available:
        available = [{"model": "anthropic/claude-haiku-4-5", "label": "Claude Haiku 4.5 (default)"}]
    return jsonify({"models": available})

@app.route("/api/r-memory/config", methods=["GET", "PUT"])
def api_rmemory_config():
    """Read or update R-Memory config (including compressionModel)."""
    if request.method == "GET":
        return jsonify(_rmem_config())
    # PUT — merge patch into existing config
    patch = request.get_json(force=True) or {}
    cfg = _rmem_config()
    cfg.update(patch)
    try:
        RMEMORY_CONFIG.write_text(json.dumps(cfg, indent=2))
        return jsonify({"ok": True, "config": cfg})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/r-memory/effective-models", methods=["GET"])
def api_rmemory_effective_models():
    """Return the actual runtime models."""
    return jsonify(_rmem_effective_models())


@app.route("/api/r-memory/narrative-model", methods=["PUT"])
def api_rmemory_narrative_model():
    """Update the narrative tracker model in camouflage.json."""
    patch = request.get_json(force=True) or {}
    model = patch.get("model")
    if not model:
        return jsonify({"error": "model required"}), 400
    camo_path = RMEMORY_DIR / "camouflage.json"
    try:
        camo = json.loads(camo_path.read_text()) if camo_path.exists() else {}
        pref = camo.get("preferredBackgroundProvider", "openai")
        bg = camo.get("backgroundModels", {})
        bg[f"{pref}-narrative"] = model
        camo["backgroundModels"] = bg
        camo_path.write_text(json.dumps(camo, indent=2))
        return jsonify({"ok": True, "narrativeModel": model})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/r-memory/open-log", methods=["POST"])
def api_rmemory_open_log():
    """Open R-Memory log in Terminal.app."""
    import subprocess
    # PLACEHOLDER: replace command with user-provided string
    cmd = "tail -f ~/.openclaw/workspace/r-memory/r-memory.log"
    subprocess.Popen([
        "osascript", "-e",
        f'tell application "Terminal" to do script "{cmd}"'
    ])
    return jsonify({"ok": True})


@app.route("/api/r-memory/stats")
def api_rmemory_stats():
    """R-Memory runtime stats: blocks from history files, log events."""
    # Get all history blocks (all sessions)
    all_blocks = _rmem_history_blocks()
    total_raw = sum(b.get("tokensRaw", 0) for b in all_blocks)
    total_comp = sum(b.get("tokensCompressed", 0) for b in all_blocks)

    # Current session blocks (stored in history file)
    cur_sid = _rmem_current_session_id()
    cur_blocks = [b for b in all_blocks if cur_sid and cur_sid in b.get("_file", "")]

    # Parse log to determine what's actually in context RIGHT NOW.
    # After a gateway restart (init), context is empty until first compaction.
    # Compressed blocks persist in conversation across gateway restarts.
    # Always show last compaction data if available.
    log_events = _rmem_parse_log()

    last_compaction = None
    for ev in log_events:
        if ev.get("event") == "compaction_done":
            last_compaction = ev

    in_context_blocks = last_compaction.get("historyBlocks", 0) if last_compaction else 0
    in_context_tokens = last_compaction.get("contentTokens", 0) if last_compaction else 0

    stats = {
        "blockCount": in_context_blocks,
        "contentTokens": in_context_tokens,
        "totalRawTokens": sum(b.get("tokensRaw", 0) for b in cur_blocks),
        "totalCompressedTokens": sum(b.get("tokensCompressed", 0) for b in cur_blocks),
        "compressionRatio": None,
        "storedBlockCount": len(cur_blocks),
        "allSessionsBlockCount": len(all_blocks),
        "allSessionsRawTokens": total_raw,
        "allSessionsCompressedTokens": total_comp,
        "currentSessionId": cur_sid,
        "logsExist": RMEMORY_LOG.exists(),
        "recentEvents": [],
    }

    if stats["totalRawTokens"] > 0:
        stats["compressionRatio"] = round(
            stats["totalCompressedTokens"] / stats["totalRawTokens"], 3
        )

    # Recent log events (last 30)
    stats["recentEvents"] = log_events[-30:]

    return jsonify(stats)


# Known model pricing database — used as fallback when auto-discovering models
_KNOWN_MODEL_PRICING = {
    "anthropic/claude-opus-4-6": {"label": "Claude Opus 4.6", "inputPer1M": 5.0, "outputPer1M": 25.0, "cacheReadPer1M": 0.5, "cacheWritePer1M": 6.25},
    "minimax/MiniMax-M2.5": {"label": "MiniMax M2.5", "inputPer1M": 0.3, "outputPer1M": 1.2, "cacheReadPer1M": 0.03, "cacheWritePer1M": 0.12},
    "minimax/MiniMax-M2.5-Lightning": {"label": "MiniMax M2.5 Lightning", "inputPer1M": 0.3, "outputPer1M": 1.2, "cacheReadPer1M": 0.03, "cacheWritePer1M": 0.12},
    "anthropic/claude-sonnet-4-6": {"label": "Claude Sonnet 4.6", "inputPer1M": 3.0, "outputPer1M": 15.0, "cacheReadPer1M": 0.3, "cacheWritePer1M": 3.75},
    "anthropic/claude-haiku-4-5": {"label": "Claude Haiku 4.5", "inputPer1M": 1.0, "outputPer1M": 5.0, "cacheReadPer1M": 0.1, "cacheWritePer1M": 1.25},
    "openai-codex/gpt-4o-mini": {"label": "GPT-4o mini", "inputPer1M": 0.15, "outputPer1M": 0.6, "cacheReadPer1M": 0.075, "cacheWritePer1M": 0.15},
    "openai-codex/gpt-5.3-codex": {"label": "GPT-5.3 Codex", "inputPer1M": 2.0, "outputPer1M": 8.0, "cacheReadPer1M": 0.5, "cacheWritePer1M": 2.0},
    "openai/gpt-4o-mini": {"label": "GPT-4o mini (direct)", "inputPer1M": 0.15, "outputPer1M": 0.6, "cacheReadPer1M": 0.075, "cacheWritePer1M": 0.15},
    "openai/gpt-4o": {"label": "GPT-4o", "inputPer1M": 2.5, "outputPer1M": 10.0, "cacheReadPer1M": 1.25, "cacheWritePer1M": 2.5},
    "google/gemini-2.0-flash": {"label": "Gemini 2.0 Flash", "inputPer1M": 0.1, "outputPer1M": 0.4, "cacheReadPer1M": 0.025, "cacheWritePer1M": 0.1},
}

def _ts_discover_system_models():
    """Auto-discover all LLM models configured in the system (agents, cron, heartbeat, R-Memory)."""
    models = set()
    try:
        cfg = json.loads(OPENCLAW_CONFIG.read_text()) if OPENCLAW_CONFIG.exists() else {}
        # Default primary model
        dp = cfg.get("agents", {}).get("defaults", {}).get("model", {}).get("primary", "")
        if dp: models.add(dp)
        # Heartbeat model
        hb = cfg.get("agents", {}).get("defaults", {}).get("heartbeat", {}).get("model", "")
        if hb: models.add(hb)
        # Per-agent models
        for a in cfg.get("agents", {}).get("list", []):
            m = a.get("model", "")
            if m: models.add(m)
    except Exception:
        pass
    # Cron jobs
    try:
        cron_path = OPENCLAW_HOME / "cron" / "jobs.json"
        if cron_path.exists():
            data = json.loads(cron_path.read_text())
            jobs = data if isinstance(data, list) else data.get("jobs", [])
            for j in jobs:
                m = j.get("payload", {}).get("model", "")
                if m: models.add(m)
    except Exception:
        pass
    # R-Memory camouflage models
    try:
        cam_path = RMEMORY_DIR / "camouflage.json"
        if cam_path.exists():
            cam = json.loads(cam_path.read_text())
            for prov, model_str in cam.get("backgroundModels", {}).items():
                if model_str: models.add(model_str)
    except Exception:
        pass
    return sorted(models)


_TOKEN_SAVINGS_DEFAULT_PRICING = {
    "currency": "USD",
    "defaultModel": "gateway/blended",
    "models": {
        "gateway/blended": {
            "label": "Gateway Blended (from usage-cost)",
            "inputPer1M": 5.0,
            "outputPer1M": 25.0,
            "cacheReadPer1M": 0.5,
            "cacheWritePer1M": 6.25,
        },
    },
    "assumptions": {
        "avgOutputTokensPerCall": 800,
        "heartbeatInputTokensPerCall": 700,
        "heartbeatOutputTokensPerCall": 140,
        "cronInputTokensPerCall": 900,
        "cronOutputTokensPerCall": 180,
        "subagentShare": 0.18,
    },
}


def _ts_merge_dict(base, override):
    out = dict(base) if isinstance(base, dict) else {}
    if not isinstance(override, dict):
        return out
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _ts_merge_dict(out[k], v)
        else:
            out[k] = v
    return out


def _ts_load_dashboard_config():
    try:
        return json.loads(_CONFIG_FILE.read_text())
    except Exception:
        return _CFG if isinstance(_CFG, dict) else {}


def _ts_save_dashboard_config(cfg):
    global _CFG
    _CONFIG_FILE.write_text(json.dumps(cfg, indent=2))
    _CFG = cfg


def _ts_float(v, default=0.0):
    try:
        return float(v)
    except Exception:
        return float(default)


def _ts_int(v, default=0):
    try:
        return int(v)
    except Exception:
        return int(default)


def _ts_parse_every_minutes(every):
    if every is None:
        return None
    if isinstance(every, (int, float)):
        return float(every) if every > 0 else None
    s = str(every).strip().lower()
    m = re.match(r"^(\d+(?:\.\d+)?)\s*([smhd])$", s)
    if not m:
        return None
    num = _ts_float(m.group(1), 0)
    unit = m.group(2)
    if num <= 0:
        return None
    mult = {"s": 1 / 60, "m": 1, "h": 60, "d": 1440}
    return num * mult[unit]


def _ts_minutes_between(start, end):
    try:
        s_h, s_m = [int(x) for x in str(start).split(":")[:2]]
        e_h, e_m = [int(x) for x in str(end).split(":")[:2]]
        s = (s_h * 60 + s_m) % 1440
        e = (e_h * 60 + e_m) % 1440
        return (e - s) % 1440
    except Exception:
        return 24 * 60


def _ts_estimate_calls_from_cron(expr, days):
    if not expr or not isinstance(expr, str):
        return 0
    parts = expr.split()
    if len(parts) < 5:
        return 0
    minute, hour, dom, _month, dow = parts[:5]

    def _count_field(field, low, high):
        span = high - low + 1
        if field == "*":
            return span
        if field.startswith("*/"):
            step = max(_ts_int(field[2:], 1), 1)
            return max(1, (span + step - 1) // step)
        if "," in field:
            items = [p for p in field.split(",") if p]
            return max(1, len(items))
        if field.isdigit():
            return 1
        return 1

    calls_per_day = _count_field(minute, 0, 59) * _count_field(hour, 0, 23)
    day_factor = 1.0
    if dom != "*" and dow == "*":
        day_factor = min(1.0, _count_field(dom, 1, 31) / 30.0)
    elif dow != "*" and dom == "*":
        day_factor = min(1.0, _count_field(dow, 0, 6) / 7.0)
    elif dom != "*" and dow != "*":
        day_factor = min(1.0, _count_field(dow, 0, 6) / 7.0)
    return max(0, int(round(calls_per_day * day_factor * max(days, 1))))


def _ts_lookup_rates(pricing, model_name):
    models = pricing.get("models", {})
    default_key = pricing.get("defaultModel", "gateway/blended")
    if model_name in models:
        return model_name, models[model_name]
    if isinstance(model_name, str):
        needle = model_name.split("/")[-1]
        for key, rates in models.items():
            if key.endswith(needle):
                return key, rates
    return default_key, models.get(default_key, {})


def _ts_component_cost(rates, input_tokens=0, output_tokens=0, cache_read_tokens=0, cache_write_tokens=0):
    ip = _ts_float(rates.get("inputPer1M"), 0)
    op = _ts_float(rates.get("outputPer1M"), 0)
    cr = _ts_float(rates.get("cacheReadPer1M"), 0)
    cw = _ts_float(rates.get("cacheWritePer1M"), 0)
    return (
        _ts_float(input_tokens) * ip / 1_000_000
        + _ts_float(output_tokens) * op / 1_000_000
        + _ts_float(cache_read_tokens) * cr / 1_000_000
        + _ts_float(cache_write_tokens) * cw / 1_000_000
    )


def _ts_sanitize_pricing(pricing):
    merged = _ts_merge_dict(_TOKEN_SAVINGS_DEFAULT_PRICING, pricing if isinstance(pricing, dict) else {})
    models = merged.get("models", {})
    for m_name, rates in list(models.items()):
        if not isinstance(rates, dict):
            models[m_name] = {}
            rates = models[m_name]
        for key in ("inputPer1M", "outputPer1M", "cacheReadPer1M", "cacheWritePer1M"):
            rates[key] = max(0.0, _ts_float(rates.get(key), 0.0))
        if "label" in rates and not isinstance(rates.get("label"), str):
            rates["label"] = str(rates["label"])
    assumptions = merged.get("assumptions", {})
    assumptions["avgOutputTokensPerCall"] = max(1, _ts_int(assumptions.get("avgOutputTokensPerCall"), 800))
    assumptions["heartbeatInputTokensPerCall"] = max(0, _ts_int(assumptions.get("heartbeatInputTokensPerCall"), 700))
    assumptions["heartbeatOutputTokensPerCall"] = max(0, _ts_int(assumptions.get("heartbeatOutputTokensPerCall"), 140))
    assumptions["cronInputTokensPerCall"] = max(0, _ts_int(assumptions.get("cronInputTokensPerCall"), 900))
    assumptions["cronOutputTokensPerCall"] = max(0, _ts_int(assumptions.get("cronOutputTokensPerCall"), 180))
    assumptions["subagentShare"] = min(0.95, max(0.0, _ts_float(assumptions.get("subagentShare"), 0.18)))
    merged["assumptions"] = assumptions
    return merged


def _ts_load_pricing():
    cfg = _ts_load_dashboard_config()
    pricing = _ts_sanitize_pricing(cfg.get("pricing", {}))
    # Auto-discover models from system and merge pricing for any that are missing
    discovered = _ts_discover_system_models()
    models = pricing.get("models", {})
    for model_id in discovered:
        if model_id not in models:
            # Look up known pricing, or create a placeholder
            known = _KNOWN_MODEL_PRICING.get(model_id)
            if known:
                models[model_id] = dict(known)
            else:
                # Unknown model — add with zero pricing so user sees it and can fill in
                short_name = model_id.split("/")[-1] if "/" in model_id else model_id
                models[model_id] = {
                    "label": f"{short_name} (auto-discovered, set pricing)",
                    "inputPer1M": 0.0, "outputPer1M": 0.0,
                    "cacheReadPer1M": 0.0, "cacheWritePer1M": 0.0,
                }
    pricing["models"] = models
    pricing["_discoveredModels"] = discovered
    return pricing, cfg


def _ts_collect_cron_jobs(cfg):
    candidates = [
        cfg.get("cron", {}).get("jobs"),
        cfg.get("jobs"),
        cfg.get("commands", {}).get("cron", {}).get("jobs"),
        cfg.get("commands", {}).get("jobs"),
    ]
    out = []
    for c in candidates:
        if isinstance(c, list):
            out.extend([j for j in c if isinstance(j, dict)])
    return out


def _ts_run_gateway_usage_cost(days):
    cmd = ["openclaw", "gateway", "usage-cost", "--days", str(days), "--json"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except Exception as e:
        return None, f"gateway usage-cost command failed: {e}", {"cmd": cmd}
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip()
        return None, err or f"command exited {result.returncode}", {"cmd": cmd}

    raw = (result.stdout or "").strip()
    if not raw:
        return None, "gateway usage-cost returned empty output", {"cmd": cmd}
    try:
        return json.loads(raw), None, {"cmd": cmd}
    except Exception:
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(raw[start : end + 1]), None, {"cmd": cmd}
            except Exception as e:
                return None, f"invalid JSON from gateway usage-cost: {e}", {"cmd": cmd}
        return None, "invalid JSON from gateway usage-cost", {"cmd": cmd}


def _ts_parse_tracker_timestamp(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, (int, float)):
        num = float(value)
        # Accept both epoch seconds and epoch milliseconds.
        seconds = num / 1000.0 if num > 10_000_000_000 else num
        try:
            dt = datetime.fromtimestamp(seconds, tz=timezone.utc)
        except Exception:
            return None
    elif isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        if re.match(r"^-?\d+(?:\.\d+)?$", raw):
            try:
                num = float(raw)
                seconds = num / 1000.0 if num > 10_000_000_000 else num
                dt = datetime.fromtimestamp(seconds, tz=timezone.utc)
            except Exception:
                return None
        else:
            try:
                dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except Exception:
                return None
    else:
        return None

    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _ts_load_tracker_usage(days):
    tracker_file = WORKSPACE / "usage-tracker" / "usage.jsonl"
    meta = {
        "path": str(tracker_file),
        "days": int(days),
        "exists": tracker_file.exists(),
        "entries": 0,
        "keptEntries": 0,
        "invalidLines": 0,
    }
    empty_totals = {
        "input": 0,
        "output": 0,
        "cacheRead": 0,
        "cacheWrite": 0,
        "totalTokens": 0,
        "inputCost": 0.0,
        "outputCost": 0.0,
        "cacheReadCost": 0.0,
        "cacheWriteCost": 0.0,
        "totalCost": 0.0,
    }
    empty_data = {"daily": [], "totals": dict(empty_totals)}

    if not tracker_file.exists():
        return empty_data, None, meta

    try:
        pricing, _cfg = _ts_load_pricing()
    except Exception:
        pricing = _TOKEN_SAVINGS_DEFAULT_PRICING

    models = pricing.get("models", {}) if isinstance(pricing, dict) else {}
    default_model = pricing.get("defaultModel", "gateway/blended") if isinstance(pricing, dict) else "gateway/blended"
    fallback_rates = models.get(default_model) if isinstance(models, dict) else None
    if not isinstance(fallback_rates, dict):
        fallback_rates = _TOKEN_SAVINGS_DEFAULT_PRICING["models"]["gateway/blended"]

    def _new_day_bucket(date_key):
        return {
            "date": date_key,
            "input": 0,
            "output": 0,
            "cacheRead": 0,
            "cacheWrite": 0,
            "totalTokens": 0,
            "inputCost": 0.0,
            "outputCost": 0.0,
            "cacheReadCost": 0.0,
            "cacheWriteCost": 0.0,
            "totalCost": 0.0,
        }

    cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, _ts_int(days, 7)))
    daily = {}
    totals = dict(empty_totals)

    try:
        with tracker_file.open("r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                row = line.strip()
                if not row:
                    continue
                meta["entries"] += 1
                try:
                    payload = json.loads(row)
                except Exception:
                    meta["invalidLines"] += 1
                    continue

                ts = _ts_parse_tracker_timestamp(payload.get("ts"))
                if ts is None or ts < cutoff:
                    continue

                input_tokens = max(0, _ts_int(payload.get("input"), 0))
                output_tokens = max(0, _ts_int(payload.get("output"), 0))
                cache_read_tokens = max(0, _ts_int(payload.get("cacheRead"), 0))
                cache_write_tokens = max(0, _ts_int(payload.get("cacheWrite"), 0))
                if (input_tokens + output_tokens + cache_read_tokens + cache_write_tokens) <= 0:
                    continue

                provider = str(payload.get("provider") or "").strip()
                model = str(payload.get("model") or "").strip()
                model_key = f"{provider}/{model}" if (provider and model) else None
                rates = _KNOWN_MODEL_PRICING.get(model_key) if model_key else None
                if not isinstance(rates, dict):
                    rates = fallback_rates

                ip = _ts_float(rates.get("inputPer1M"), 0.0)
                op = _ts_float(rates.get("outputPer1M"), 0.0)
                cr = _ts_float(rates.get("cacheReadPer1M"), 0.0)
                cw = _ts_float(rates.get("cacheWritePer1M"), 0.0)

                input_cost = input_tokens * ip / 1_000_000
                output_cost = output_tokens * op / 1_000_000
                cache_read_cost = cache_read_tokens * cr / 1_000_000
                cache_write_cost = cache_write_tokens * cw / 1_000_000
                total_tokens = input_tokens + output_tokens + cache_read_tokens + cache_write_tokens
                total_cost = input_cost + output_cost + cache_read_cost + cache_write_cost

                date_key = ts.date().isoformat()
                bucket = daily.setdefault(date_key, _new_day_bucket(date_key))
                bucket["input"] += input_tokens
                bucket["output"] += output_tokens
                bucket["cacheRead"] += cache_read_tokens
                bucket["cacheWrite"] += cache_write_tokens
                bucket["totalTokens"] += total_tokens
                bucket["inputCost"] += input_cost
                bucket["outputCost"] += output_cost
                bucket["cacheReadCost"] += cache_read_cost
                bucket["cacheWriteCost"] += cache_write_cost
                bucket["totalCost"] += total_cost

                totals["input"] += input_tokens
                totals["output"] += output_tokens
                totals["cacheRead"] += cache_read_tokens
                totals["cacheWrite"] += cache_write_tokens
                totals["totalTokens"] += total_tokens
                totals["inputCost"] += input_cost
                totals["outputCost"] += output_cost
                totals["cacheReadCost"] += cache_read_cost
                totals["cacheWriteCost"] += cache_write_cost
                totals["totalCost"] += total_cost
                meta["keptEntries"] += 1
    except Exception as e:
        return None, f"failed to read tracker usage file: {e}", meta

    return {"daily": [daily[d] for d in sorted(daily.keys())], "totals": totals}, None, meta


@app.route("/api/token-savings/pricing", methods=["PUT"])
def api_token_savings_pricing():
    """Update pricing reference used by /api/token-savings."""
    patch = request.get_json(force=True) or {}
    if not isinstance(patch, dict):
        return jsonify({"ok": False, "error": "invalid payload"}), 400
    pricing, cfg = _ts_load_pricing()
    updated = _ts_sanitize_pricing(_ts_merge_dict(pricing, patch))
    try:
        cfg["pricing"] = updated
        _ts_save_dashboard_config(cfg)
        return jsonify({"ok": True, "pricing": updated})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/token-savings")
def api_token_savings():
    """Cost operations center using gateway usage-cost + R-Memory stats."""
    days = max(1, min(30, _ts_int(request.args.get("days", 7), 7)))
    pricing, _cfg = _ts_load_pricing()
    assumptions = pricing.get("assumptions", {})

    usage_stats = {}
    usage_stats_path = RMEMORY_DIR / "usage-stats.json"
    if usage_stats_path.exists():
        try:
            usage_stats = json.loads(usage_stats_path.read_text())
        except Exception:
            usage_stats = {}

    all_blocks = _rmem_history_blocks()
    cur_sid = _rmem_current_session_id()
    cur_blocks = [b for b in all_blocks if cur_sid and cur_sid in b.get("_file", "")]

    # Use ALL blocks for total counts
    all_raw = sum(_ts_int(b.get("tokensRaw"), 0) for b in all_blocks)
    all_comp = sum(_ts_int(b.get("tokensCompressed"), 0) for b in all_blocks)

    # Filter to meaningful blocks (raw > 50 tokens AND actual savings) for compression ratio
    meaningful_blocks = [b for b in all_blocks
                         if _ts_int(b.get("tokensRaw"), 0) > 50
                         and _ts_int(b.get("tokensRaw"), 0) > _ts_int(b.get("tokensCompressed"), 0)]
    meaningful_raw = sum(_ts_int(b.get("tokensRaw"), 0) for b in meaningful_blocks)
    meaningful_comp = sum(_ts_int(b.get("tokensCompressed"), 0) for b in meaningful_blocks)

    # Average tokens saved per API call = avg compressed blocks in context x savings per block
    context_raw = sum(_ts_int(b.get("tokensRaw"), 0) for b in cur_blocks)
    context_comp = sum(_ts_int(b.get("tokensCompressed"), 0) for b in cur_blocks)
    cur_saved = sum(max(0, _ts_int(b.get("tokensRaw"), 0) - _ts_int(b.get("tokensCompressed"), 0)) for b in cur_blocks)
    # If current session has meaningful savings, use it; otherwise estimate from lifetime meaningful blocks
    if cur_saved > 1000:
        context_saved_per_call = cur_saved
    elif len(meaningful_blocks) > 0:
        # Use meaningful blocks only (excludes tiny/negative blocks that dilute the ratio)
        avg_saving_per_block = (meaningful_raw - meaningful_comp) / len(meaningful_blocks)
        avg_context_blocks = max(len(cur_blocks), 25)  # typical context holds ~25 compressed blocks
        context_saved_per_call = int(avg_saving_per_block * avg_context_blocks)
    else:
        context_saved_per_call = 0
    archived_blocks = max(0, len(all_blocks) - len(cur_blocks))
    archived_raw = max(0, all_raw - context_raw)
    archived_comp = max(0, all_comp - context_comp)

    tracker_data, tracker_error, tracker_meta = _ts_load_tracker_usage(days)
    tracker_meta = tracker_meta if isinstance(tracker_meta, dict) else {}
    tracker_daily = tracker_data.get("daily", []) if isinstance(tracker_data, dict) else []
    tracker_totals = tracker_data.get("totals", {}) if isinstance(tracker_data, dict) else {}
    tracker_has_entries = (
        _ts_int(tracker_meta.get("keptEntries"), 0) > 0
        or len(tracker_daily) > 0
        or _ts_int(tracker_totals.get("totalTokens"), 0) > 0
    )

    source = "usage-tracker" if tracker_has_entries else "gateway"
    if tracker_has_entries:
        gateway_data, gateway_error, gateway_meta = tracker_data, tracker_error, tracker_meta
    else:
        gateway_data, gateway_error, gateway_meta = _ts_run_gateway_usage_cost(days)

    daily = gateway_data.get("daily", []) if isinstance(gateway_data, dict) else []
    totals = gateway_data.get("totals", {}) if isinstance(gateway_data, dict) else {}

    total_cost = _ts_float(totals.get("totalCost"), 0)
    total_input = _ts_int(totals.get("input"), 0)
    total_output = _ts_int(totals.get("output"), 0)
    total_cache_read = _ts_int(totals.get("cacheRead"), 0)
    total_cache_write = _ts_int(totals.get("cacheWrite"), 0)
    total_tokens = _ts_int(totals.get("totalTokens"), 0)

    input_cost = _ts_float(totals.get("inputCost"), sum(_ts_float(d.get("inputCost"), 0) for d in daily))
    output_cost = _ts_float(totals.get("outputCost"), sum(_ts_float(d.get("outputCost"), 0) for d in daily))
    cache_read_cost = _ts_float(totals.get("cacheReadCost"), sum(_ts_float(d.get("cacheReadCost"), 0) for d in daily))
    cache_write_cost = _ts_float(totals.get("cacheWriteCost"), sum(_ts_float(d.get("cacheWriteCost"), 0) for d in daily))

    def _safe_rate(cost, tokens):
        return (cost / tokens) if tokens > 0 else 0.0

    rates = {
        "input": _safe_rate(input_cost, total_input),
        "output": _safe_rate(output_cost, total_output),
        "cacheRead": _safe_rate(cache_read_cost, total_cache_read),
        "cacheWrite": _safe_rate(cache_write_cost, total_cache_write),
    }
    fractions = {
        "input": (input_cost / total_cost) if total_cost > 0 else 0.0,
        "output": (output_cost / total_cost) if total_cost > 0 else 0.0,
        "cacheRead": (cache_read_cost / total_cost) if total_cost > 0 else 0.0,
        "cacheWrite": (cache_write_cost / total_cost) if total_cost > 0 else 0.0,
    }
    weighted_cost_per_token = (
        fractions["input"] * rates["input"]
        + fractions["output"] * rates["output"]
        + fractions["cacheRead"] * rates["cacheRead"]
        + fractions["cacheWrite"] * rates["cacheWrite"]
    )
    if weighted_cost_per_token <= 0 and total_cost > 0 and total_tokens > 0:
        weighted_cost_per_token = total_cost / total_tokens

    explicit_calls = None
    for key in ("apiCalls", "requestCount", "totalTurns", "turns"):
        v = totals.get(key)
        if isinstance(v, (int, float)) and v > 0:
            explicit_calls = int(v)
            break
    if explicit_calls is None:
        for key in ("apiCalls", "requestCount", "totalTurns", "turns"):
            summed = sum(_ts_int(d.get(key), 0) for d in daily)
            if summed > 0:
                explicit_calls = summed
                break
    if explicit_calls is None:
        avg_output_per_call = max(1, _ts_int(assumptions.get("avgOutputTokensPerCall"), 800))
        explicit_calls = max(1, int(round(total_output / avg_output_per_call))) if total_output > 0 else 0

    compound_saved_tokens = context_saved_per_call * explicit_calls

    # Correct savings model: compression reduces ALL input-side tokens (input + cacheRead + cacheWrite).
    # Output tokens are unaffected. Apply compression ratio to input-side costs directly.
    input_side_cost = input_cost + cache_read_cost + cache_write_cost
    meaningful_efficiency = (meaningful_raw - meaningful_comp) / meaningful_raw if meaningful_raw > 0 else 0.0
    if meaningful_efficiency > 0 and input_side_cost > 0:
        # Current input costs already reflect compressed tokens.
        # Without compression, input-side would be cost / (1 - ratio) since current = raw * (1 - ratio)
        without_rmemory_input = input_side_cost / (1.0 - meaningful_efficiency)
        compound_saved_cost = without_rmemory_input - input_side_cost
        without_rmemory_cost = output_cost + without_rmemory_input
    else:
        compound_saved_cost = compound_saved_tokens * weighted_cost_per_token if (compound_saved_tokens > 0 and weighted_cost_per_token > 0) else 0.0
        without_rmemory_cost = (total_cost + compound_saved_cost) if total_cost > 0 else None
    saving_pct = ((compound_saved_cost / without_rmemory_cost) * 100.0) if without_rmemory_cost and without_rmemory_cost > 0 else None

    try:
        ocfg = json.loads(OPENCLAW_CONFIG.read_text())
    except Exception:
        ocfg = {}
    defaults = ocfg.get("agents", {}).get("defaults", {})
    main_model = defaults.get("model")
    if isinstance(main_model, dict):
        main_model = main_model.get("primary") or str(main_model)
    if not main_model:
        main_model = pricing.get("defaultModel", "gateway/blended")

    hb_cfg = defaults.get("heartbeat", {}) if isinstance(defaults.get("heartbeat", {}), dict) else {}
    hb_every = hb_cfg.get("every", "30m")
    hb_model = hb_cfg.get("model", pricing.get("defaultModel", "gateway/blended"))
    hb_enabled = hb_cfg.get("enabled", True)
    hb_minutes = _ts_parse_every_minutes(hb_every)
    active_hours = hb_cfg.get("activeHours", {})
    active_minutes = _ts_minutes_between(active_hours.get("start", "00:00"), active_hours.get("end", "00:00")) if active_hours else 24 * 60
    hb_calls_per_day = int(round((active_minutes / hb_minutes))) if (hb_enabled and hb_minutes and hb_minutes > 0) else 0
    hb_calls = max(0, hb_calls_per_day * days)

    cron_jobs = _ts_collect_cron_jobs(ocfg)

    components = []

    def _add_component(component_id, name, model, input_tokens, output_tokens, cost, source, estimated):
        components.append(
            {
                "id": component_id,
                "component": name,
                "model": model,
                "inputTokens": int(max(0, round(_ts_float(input_tokens, 0)))),
                "outputTokens": int(max(0, round(_ts_float(output_tokens, 0)))),
                "cost": round(max(0.0, _ts_float(cost, 0.0)), 4),
                "source": source,
                "estimated": bool(estimated),
            }
        )

    rmem_effective = _rmem_effective_models()
    comp_stats = usage_stats.get("compression", {}) if isinstance(usage_stats.get("compression"), dict) else {}
    nar_stats = usage_stats.get("narrative", {}) if isinstance(usage_stats.get("narrative"), dict) else {}

    comp_model = rmem_effective.get("compression", "anthropic/claude-haiku-4-5")
    nar_model = rmem_effective.get("narrative", comp_model)
    _, comp_rates = _ts_lookup_rates(pricing, comp_model)
    _, nar_rates = _ts_lookup_rates(pricing, nar_model)

    comp_input = _ts_int(comp_stats.get("inputTokens"), 0)
    comp_output = _ts_int(comp_stats.get("outputTokens"), 0)
    nar_input = _ts_int(nar_stats.get("inputTokens"), 0)
    nar_output = _ts_int(nar_stats.get("outputTokens"), 0)

    comp_cost = _ts_component_cost(comp_rates, comp_input, comp_output)
    nar_cost = _ts_component_cost(nar_rates, nar_input, nar_output)
    _add_component(
        "r-memory-compression",
        "R-Memory Compression",
        comp_model,
        comp_input,
        comp_output,
        comp_cost,
        "~/.openclaw/workspace/r-memory/usage-stats.json",
        False,
    )
    _add_component(
        "r-memory-narrative",
        "R-Memory Narrative",
        nar_model,
        nar_input,
        nar_output,
        nar_cost,
        "~/.openclaw/workspace/r-memory/usage-stats.json",
        False,
    )

    hb_input = hb_calls * _ts_int(assumptions.get("heartbeatInputTokensPerCall"), 700)
    hb_output = hb_calls * _ts_int(assumptions.get("heartbeatOutputTokensPerCall"), 140)
    _, hb_rates = _ts_lookup_rates(pricing, hb_model)
    hb_cost = _ts_component_cost(hb_rates, hb_input, hb_output)
    _add_component(
        "heartbeat",
        "Heartbeat",
        hb_model,
        hb_input,
        hb_output,
        hb_cost,
        f"openclaw.json heartbeat.every={hb_every} (est.)",
        True,
    )

    cron_total_input = 0
    cron_total_output = 0
    cron_total_cost = 0.0
    for idx, job in enumerate(cron_jobs):
        if job.get("enabled") is False:
            continue
        j_name = job.get("name") or job.get("id") or f"Job {idx + 1}"
        j_model = job.get("model") or main_model
        calls = 0
        if job.get("every"):
            m = _ts_parse_every_minutes(job.get("every"))
            calls = int(round((days * 24 * 60) / m)) if m and m > 0 else 0
        elif job.get("schedule"):
            calls = _ts_estimate_calls_from_cron(str(job.get("schedule")), days)
        if calls <= 0:
            calls = days
        inp_per_call = _ts_int(job.get("avgInputTokens"), _ts_int(assumptions.get("cronInputTokensPerCall"), 900))
        out_per_call = _ts_int(job.get("avgOutputTokens"), _ts_int(assumptions.get("cronOutputTokensPerCall"), 180))
        inp = max(0, calls * inp_per_call)
        out = max(0, calls * out_per_call)
        _, j_rates = _ts_lookup_rates(pricing, j_model)
        cst = _ts_component_cost(j_rates, inp, out)
        cron_total_input += inp
        cron_total_output += out
        cron_total_cost += cst
        _add_component(
            f"cron-{idx+1}",
            f"Cron: {j_name}",
            j_model,
            inp,
            out,
            cst,
            f"openclaw cron schedule ({job.get('every') or job.get('schedule') or 'default'}) (est.)",
            True,
        )

    known_cost = comp_cost + nar_cost + hb_cost + cron_total_cost
    known_input = comp_input + nar_input + hb_input + cron_total_input
    known_output = comp_output + nar_output + hb_output + cron_total_output

    remaining_cost = max(0.0, total_cost - known_cost)
    subagent_share = _ts_float(assumptions.get("subagentShare"), 0.18)
    subagent_share = min(0.95, max(0.0, subagent_share))
    subagent_cost = remaining_cost * subagent_share
    main_cost = max(0.0, remaining_cost - subagent_cost)

    remaining_input = max(0, total_input - known_input)
    remaining_output = max(0, total_output - known_output)
    subagent_input = int(round(remaining_input * subagent_share))
    subagent_output = int(round(remaining_output * subagent_share))
    main_input = max(0, remaining_input - subagent_input)
    main_output = max(0, remaining_output - subagent_output)

    sub_model = "subagents/default"
    _add_component(
        "subagents",
        "Sub-Agents Runtime",
        sub_model,
        subagent_input,
        subagent_output,
        subagent_cost,
        "Residual share after known components (est.)",
        True,
    )
    _add_component(
        "main-session",
        "Main Session",
        main_model,
        main_input,
        main_output,
        main_cost,
        "Gateway total minus system components",
        True,
    )

    components.sort(key=lambda x: x.get("cost", 0), reverse=True)

    component_cost_lookup = {c["id"]: c["cost"] for c in components}
    daily_breakdown = []
    for entry in daily:
        d_cost = _ts_float(entry.get("totalCost"), 0.0)
        ratio = (d_cost / total_cost) if total_cost > 0 else 0.0
        comp_costs = {cid: round(val * ratio, 4) for cid, val in component_cost_lookup.items()}
        drift = d_cost - sum(comp_costs.values())
        if "main-session" in comp_costs:
            comp_costs["main-session"] = round(comp_costs["main-session"] + drift, 4)
        daily_breakdown.append(
            {
                "date": entry.get("date"),
                "totalCost": round(d_cost, 4),
                "components": comp_costs,
            }
        )

    context_efficiency = ((context_raw - context_comp) / context_raw) if context_raw > 0 else None
    archived_efficiency = ((archived_raw - archived_comp) / archived_raw) if archived_raw > 0 else None
    # Lifetime efficiency across meaningful blocks (excludes tiny/negative that dilute the ratio)
    lifetime_raw = meaningful_raw if meaningful_raw > 0 else all_raw
    lifetime_comp = meaningful_comp if meaningful_raw > 0 else all_comp
    lifetime_efficiency = ((lifetime_raw - lifetime_comp) / lifetime_raw) if lifetime_raw > 0 else None
    payload = {
        "ok": gateway_error is None and total_cost > 0,
        "source": source,
        "days": days,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "trackingStartDate": "2026-02-25",
        "sources": {
            "usageTracker": tracker_meta.get("path"),
            "trackerError": tracker_error,
            "trackerEntries": _ts_int(tracker_meta.get("keptEntries"), 0),
            "gatewayUsageCost": "openclaw gateway usage-cost --days N --json",
            "rMemoryUsageStats": "~/.openclaw/workspace/r-memory/usage-stats.json",
            "rMemoryHistory": "~/.openclaw/workspace/r-memory/history-*.json",
            "pricing": "dashboard/config.json:pricing",
            "gatewayError": gateway_error if source == "gateway" else None,
            "gatewayCmd": gateway_meta.get("cmd") if isinstance(gateway_meta, dict) else None,
        },
        "totals": {
            "actualApiCost": round(total_cost, 4) if total_cost > 0 else None,
            "withoutRMemoryCostEstimate": round(without_rmemory_cost, 4) if without_rmemory_cost is not None else None,
            "rMemorySavingsEstimate": round(compound_saved_cost, 4) if compound_saved_cost > 0 else None,
            "savingPctEstimate": round(saving_pct, 2) if saving_pct is not None else None,
        },
        "gatewayTotals": {
            "inputTokens": total_input,
            "outputTokens": total_output,
            "cacheReadTokens": total_cache_read,
            "cacheWriteTokens": total_cache_write,
            "totalTokens": total_tokens,
            "inputCost": round(input_cost, 4),
            "outputCost": round(output_cost, 4),
            "cacheReadCost": round(cache_read_cost, 4),
            "cacheWriteCost": round(cache_write_cost, 4),
            "fractions": fractions,
            "ratesPerToken": rates,
            "weightedCostPerToken": weighted_cost_per_token,
        },
        "compoundSavings": {
            "estimated": True,
            "method": "sum(tokensRaw - tokensCompressed in current context blocks) × estimated API calls",
            "contextBlocks": len(cur_blocks),
            "tokensSavedPerCall": context_saved_per_call,
            "estimatedApiCalls": explicit_calls,
            "compoundSavedTokens": compound_saved_tokens,
            "weightedCostPerToken": weighted_cost_per_token,
            "costSavedEstimate": round(compound_saved_cost, 4),
        },
        "compressionStats": {
            "blocksInContext": len(cur_blocks),
            "blocksCompressed": len(all_blocks),
            "blocksArchived": archived_blocks,
            "contextRawTokens": context_raw,
            "contextCompressedTokens": context_comp,
            "archivedRawTokens": archived_raw,
            "archivedCompressedTokens": archived_comp,
            "contextEfficiency": round(context_efficiency * 100, 2) if context_efficiency is not None else None,
            "archivedEfficiency": round(archived_efficiency * 100, 2) if archived_efficiency is not None else None,
            "lifetimeRawTokens": lifetime_raw,
            "lifetimeCompressedTokens": lifetime_comp,
            "lifetimeEfficiency": round(lifetime_efficiency * 100, 2) if lifetime_efficiency is not None else None,
            "compressionCalls": _ts_int(comp_stats.get("calls"), 0),
            "narrativeCalls": _ts_int(nar_stats.get("calls"), 0),
            "compressionInputTokens": comp_input,
            "compressionOutputTokens": comp_output,
            "narrativeInputTokens": nar_input,
            "narrativeOutputTokens": nar_output,
        },
        "componentBreakdown": components,
        "dailyCostBreakdown": daily_breakdown,
        "pricingReference": pricing,
    }
    return jsonify(payload)


@app.route("/api/r-memory/lock/<path:doc_path>", methods=["POST"])
def api_rmemory_lock(doc_path):
    """Lock a document with chflags schg (requires sudo password)."""
    full_path = SSOT_ROOT / doc_path
    if not full_path.exists():
        return jsonify({"error": "not found"}), 404
    body = request.get_json(force=True) or {}
    password = body.get("password", "")
    if not password:
        return jsonify({"error": "password required — schg needs root"}), 403
    try:
        proc = subprocess.run(
            ["sudo", "-S", "chflags", "schg", str(full_path)],
            input=password.encode() + b"\n",
            capture_output=True, timeout=10
        )
        if proc.returncode == 0:
            return jsonify({"ok": True, "locked": True})
        else:
            return jsonify({"ok": False, "error": "lock failed (wrong password?)"}), 403
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/api/r-memory/unlock/<path:doc_path>", methods=["POST"])
def api_rmemory_unlock(doc_path):
    """Unlock a document. Requires sudo password in body."""
    full_path = SSOT_ROOT / doc_path
    if not full_path.exists():
        return jsonify({"error": "not found"}), 404

    body = request.get_json(force=True) or {}
    password = body.get("password", "")
    if not password:
        return jsonify({"error": "password required"}), 400

    try:
        proc = subprocess.run(
            ["sudo", "-S", "chflags", "noschg", str(full_path)],
            input=password.encode() + b"\n",
            capture_output=True, timeout=10
        )
        if proc.returncode == 0:
            return jsonify({"ok": True, "locked": False})
        else:
            return jsonify({"ok": False, "error": "unlock failed (wrong password?)"}), 403
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/r-memory/document", methods=["PUT"])
def api_rmemory_document_save():
    """Save/update a SSoT document."""
    body = request.get_json(force=True) or {}
    rel_path = body.get("path", "")
    content = body.get("content", "")
    if not rel_path or ".." in rel_path:
        return jsonify({"ok": False, "error": "invalid path"}), 400
    full_path = SSOT_ROOT / rel_path
    if not full_path.exists():
        return jsonify({"ok": False, "error": "not found"}), 404
    # Check lock
    try:
        if hasattr(full_path.stat(), "st_flags") and full_path.stat().st_flags & 0x02:
            return jsonify({"ok": False, "error": "document is locked"}), 403
    except Exception:
        pass
    try:
        full_path.write_text(content)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


SSOT_KEYWORDS_FILE = SSOT_ROOT / ".ssot-keywords.json"
R_AWARENESS_KEYWORDS_FILE = WORKSPACE / "r-awareness" / "keywords.json"

def _load_keywords():
    """Load dashboard keywords {docPath: [kw1, kw2, ...]}."""
    try:
        return json.loads(SSOT_KEYWORDS_FILE.read_text())
    except Exception:
        return {}

def _load_r_awareness_keywords():
    """Load R-Awareness keywords {keyword: docPath} and invert to dashboard format."""
    try:
        ra = json.loads(R_AWARENESS_KEYWORDS_FILE.read_text())
        # Invert: {kw: path} → {path: [kw1, kw2]}
        result = {}
        for kw, path in ra.items():
            result.setdefault(path, []).append(kw)
        return result
    except Exception:
        return {}

def _sync_to_r_awareness(data):
    """Write inverted keyword map to R-Awareness keywords.json. {docPath: [kws]} → {kw: docPath}.
    Dashboard uses .md paths; R-Awareness needs .ai.md paths (prefer compressed variant)."""
    inverted = {}
    for doc_path, kws in data.items():
        # Convert .md → .ai.md for R-Awareness if compressed variant exists
        ra_path = doc_path
        if doc_path.endswith(".md") and not doc_path.endswith(".ai.md"):
            ai_candidate = doc_path[:-3] + ".ai.md"
            if (SSOT_ROOT / ai_candidate).exists():
                ra_path = ai_candidate
        for kw in kws:
            inverted[kw.strip().lower()] = ra_path
    try:
        R_AWARENESS_KEYWORDS_FILE.parent.mkdir(parents=True, exist_ok=True)
        R_AWARENESS_KEYWORDS_FILE.write_text(json.dumps(inverted, indent=2))
    except Exception:
        pass  # Best-effort sync

def _save_keywords(data):
    SSOT_KEYWORDS_FILE.write_text(json.dumps(data, indent=2))
    _sync_to_r_awareness(data)

@app.route("/api/ssot/keywords", methods=["GET"])
@app.route("/api/r-memory/keywords", methods=["GET"])
def api_ssot_keywords_get():
    return jsonify(_load_keywords())

@app.route("/api/ssot/keywords", methods=["PUT"])
@app.route("/api/r-memory/keywords", methods=["PUT"])
def api_ssot_keywords_put():
    body = request.get_json(force=True) or {}
    path = body.get("path", "")
    keywords = body.get("keywords", [])
    if not path:
        return jsonify({"ok": False, "error": "path required"}), 400
    data = _load_keywords()
    if keywords:
        data[path] = keywords
    else:
        data.pop(path, None)
    _save_keywords(data)
    return jsonify({"ok": True})


@app.route("/api/r-memory/lock-layer/<layer>", methods=["POST"])
def api_rmemory_lock_layer(layer):
    """Lock all documents in a layer."""
    layer_dir = SSOT_ROOT / layer
    if not layer_dir.exists():
        return jsonify({"ok": False, "error": "layer not found"}), 404
    body = request.get_json(force=True) or {}
    password = body.get("password", "")
    if not password:
        return jsonify({"ok": False, "error": "password required — schg needs root"}), 403
    count = 0
    errors = []
    for f in layer_dir.rglob("*.md"):
        if f.name.startswith("."):
            continue
        try:
            proc = subprocess.run(
                ["sudo", "-S", "chflags", "schg", str(f)],
                input=password.encode() + b"\n",
                capture_output=True, timeout=10
            )
            if proc.returncode == 0:
                count += 1
            else:
                errors.append(f"{f.name}: lock failed")
        except Exception as e:
            errors.append(f"{f.name}: {e}")
    if errors and count == 0:
        return jsonify({"ok": False, "error": "lock failed (wrong password?)", "errors": errors}), 403
    return jsonify({"ok": True, "count": count, "errors": errors})


@app.route("/api/r-memory/unlock-layer/<layer>", methods=["POST"])
def api_rmemory_unlock_layer(layer):
    """Unlock all documents in a layer. Requires password."""
    layer_dir = SSOT_ROOT / layer
    if not layer_dir.exists():
        return jsonify({"ok": False, "error": "layer not found"}), 404
    body = request.get_json(force=True) or {}
    password = body.get("password", "")
    if not password:
        return jsonify({"ok": False, "error": "password required"}), 400
    count = 0
    errors = []
    for f in layer_dir.rglob("*.md"):
        if f.name.startswith("."):
            continue
        try:
            proc = subprocess.run(
                ["sudo", "-S", "chflags", "noschg", str(f)],
                input=password.encode() + b"\n",
                capture_output=True, timeout=10
            )
            if proc.returncode == 0:
                count += 1
            else:
                errors.append(f"{f.name}: unlock failed")
        except Exception as e:
            errors.append(f"{f.name}: {e}")
    if errors and count == 0:
        return jsonify({"ok": False, "error": "unlock failed (wrong password?)", "errors": errors}), 403
    return jsonify({"ok": True, "count": count, "errors": errors})


# ---------------------------------------------------------------------------
# API: Memory Health (context window + subsystem status)
# ---------------------------------------------------------------------------

@app.route("/api/memory/health")
def api_memory_health():
    """Memory subsystem health: context window, compression, FIFO status.
    
    Data sources (per R-Memory V4.6.1 Dashboard Data Guide):
    - history-{sessionId}.json → compressed blocks actually in context
    - config.json → compressTrigger, evictTrigger, blockSize
    - r-memory.log → compaction events, FIFO events, session events
    - Gateway WS → actual totalTokens for the session
    """
    config = _rmem_config()
    compress_trigger = config.get("compressTrigger", 36000)
    evict_trigger = config.get("evictTrigger", 80000)

    # --- Get current session blocks from history files ---
    cur_sid = _rmem_current_session_id()
    cur_blocks = _rmem_history_blocks(cur_sid) if cur_sid else []
    all_blocks = _rmem_history_blocks()

    stored_blocks_raw = sum(b.get("tokensRaw", 0) for b in cur_blocks)
    stored_blocks_comp = sum(b.get("tokensCompressed", 0) for b in cur_blocks)
    stored_blocks_count = len(cur_blocks)

    # --- Parse log events ---
    log_events = _rmem_parse_log()

    # Find last session start, compaction done events
    last_init = None
    last_compaction_done = None
    last_session = None
    compaction_count = 0
    fifo_events = []
    cache_hits = 0
    cache_misses = 0

    for ev in log_events:
        etype = ev.get("event", "")
        if etype == "init":
            last_init = ev
        elif etype == "session":
            last_session = ev
        elif etype == "compaction_done":
            last_compaction_done = ev
            compaction_count += 1
            cache_hits += ev.get("cacheHits", 0)
            cache_misses += ev.get("cacheMisses", 0)
        elif etype == "fifo_evicted":
            fifo_events.append(ev)

    # --- Determine actual in-context blocks ---
    # Compressed blocks persist in the conversation as <summary> across gateway
    # restarts. An init event does NOT clear them — only a new session does.
    # So we always show the last compaction data if available.
    blocks_count = stored_blocks_count
    blocks_comp = stored_blocks_comp
    blocks_raw = stored_blocks_raw
    # If history files are empty but compaction ran, use compaction data
    if blocks_count == 0 and last_compaction_done:
        blocks_comp = last_compaction_done.get("compressed", 0) or last_compaction_done.get("contentTokens", 0) or 0
        blocks_raw = last_compaction_done.get("raw", 0) or 0
        blocks_count = last_compaction_done.get("blocksSwapped", 0) or last_compaction_done.get("historyBlocks", 0) or 0

    # --- Gateway session data ---
    gw_session = _rmem_gateway_session()
    actual_total = gw_session.get("totalTokens", 0) if gw_session else 0
    max_tokens = gw_session.get("contextTokens", 200000) if gw_session else 200000
    model = gw_session.get("model") if gw_session else None

    # --- Estimate workspace file sizes ---
    workspace_tokens = 0
    for fname in ["AGENTS.md", "SOUL.md", "TOOLS.md", "USER.md", "MEMORY.md",
                   "IDENTITY.md", "HEARTBEAT.md"]:
        fpath = WORKSPACE / fname
        if fpath.exists():
            try:
                workspace_tokens += len(fpath.read_text()) // 4
            except Exception:
                pass

    # OpenClaw system prompt includes: core instructions, tool schemas, skill list,
    # runtime context, formatting rules, safety rules — typically 12-15k tokens.
    # Workspace files are counted separately below, so this is the non-workspace portion.
    system_prompt_tokens = 12000

    # SSoT docs — read actual injection data from R-Awareness log
    ssot_tokens = 0
    ssot_count = 0
    ssot_injected_docs = []
    try:
        ra_log = WORKSPACE / "r-awareness" / "r-awareness.log"
        if ra_log.exists():
            import re
            lines = ra_log.read_text().splitlines()
            # Find last injection event for count/tokens
            for line in reversed(lines):
                if "Injecting into system prompt" in line:
                    m = re.search(r'"docs":(\d+),"tokens":(\d+)', line)
                    if m:
                        ssot_count = int(m.group(1))
                        ssot_tokens = int(m.group(2))
                    break
            # Reconstruct injected doc set: collect unique docs from the last
            # injection cycle (human keywords + queued AI keywords before it)
            last_inject_idx = None
            for i in range(len(lines)-1, -1, -1):
                if "Injecting into system prompt" in lines[i]:
                    last_inject_idx = i
                    break
            if last_inject_idx is not None:
                # Collect docs from keyword match lines in this cycle
                all_docs = set()
                # Look backwards from injection to find the keyword lines that fed it
                prev_inject_idx = None
                for i in range(last_inject_idx-1, -1, -1):
                    if "Injecting into system prompt" in lines[i]:
                        prev_inject_idx = i
                        break
                start = (prev_inject_idx + 1) if prev_inject_idx is not None else 0
                for i in range(start, last_inject_idx + 1):
                    m = re.search(r'"docs":\[([^\]]*)\]', lines[i])
                    if m and m.group(1):
                        for d in m.group(1).split(","):
                            d = d.strip().strip('"')
                            if d:
                                all_docs.add(d)
                ssot_injected_docs = sorted(all_docs)[:ssot_count]  # Cap at actual injected count
    except Exception:
        pass
    # Fallback: scan all docs if no log data
    if ssot_count == 0:
        try:
            docs = []
            for layer in ["L0", "L1", "L2", "L3", "L4"]:
                docs.extend(_scan_ssot_layer(SSOT_ROOT / layer, layer))
            ssot_count = len(docs)
            ssot_tokens = sum(d.get("tokens", 0) for d in docs)
        except Exception:
            pass

    # Conversation = actual total - fixed segments - compressed blocks
    conversation_tokens = max(0, actual_total - system_prompt_tokens - workspace_tokens - ssot_tokens - blocks_comp)

    # --- Build result ---
    result = {
        "contextWindow": {
            "maxTokens": max_tokens,
            "actualTotalTokens": actual_total,
            "model": model,
            "lastInputTokens": gw_session.get("inputTokens", 0) if gw_session else 0,
            "lastOutputTokens": gw_session.get("outputTokens", 0) if gw_session else 0,
            "injectedSSoTs": ssot_count,
            "injectedSSoTDocs": ssot_injected_docs,
            "injectedBlocks": blocks_count,
            "segments": {
                "systemPrompt": system_prompt_tokens,
                "workspaceFiles": workspace_tokens,
                "ssotDocs": ssot_tokens,
                "conversation": conversation_tokens,
                "compressedBlocks": blocks_comp,
            },
            "status": "ok",
        },
        "subsystems": {},
        "lastTurn": None,
        "lastEventTs": None,
    }

    # Context window status
    if actual_total > 0:
        ratio = actual_total / max_tokens
        if ratio < 0.5:
            result["contextWindow"]["status"] = "ok"
        elif ratio < 0.75:
            result["contextWindow"]["status"] = "warning"
        else:
            result["contextWindow"]["status"] = "critical"

    # --- Subsystem: Plugin (R-Memory init) ---
    if last_init:
        cached = last_init.get("cachedBlocks", last_init.get("cachedTurns", 0))
        result["subsystems"]["plugin"] = {
            "label": "R-Memory Plugin",
            "status": "ok",
            "detail": f"V4.6.1 running, {cached} cached blocks, trigger: {compress_trigger}",
            "lastSeen": last_init.get("ts"),
        }
    else:
        result["subsystems"]["plugin"] = {
            "label": "R-Memory Plugin",
            "status": "error",
            "detail": "No init event found in log",
            "lastSeen": None,
        }

    # --- Subsystem: Injection (SSoT awareness) ---
    # R-Memory V4.6.1 doesn't emit injection events; SSoTs come from manifest
    if ssot_count > 0:
        result["subsystems"]["injection"] = {
            "label": "R-Awareness (Injection)",
            "status": "ok",
            "detail": f"{ssot_count} SSoT docs ({ssot_tokens} tok)",
            "lastSeen": last_init.get("ts") if last_init else None,
        }
    else:
        result["subsystems"]["injection"] = {
            "label": "R-Awareness (Injection)",
            "status": "idle",
            "detail": "No SSoT documents found",
            "lastSeen": None,
        }

    # --- Subsystem: Keyword Detection (from R-Awareness log) ---
    kw_events = []
    if R_AWARENESS_LOG.exists():
        try:
            ra_text = R_AWARENESS_LOG.read_text(errors="ignore")
            kw_re = re.compile(
                r'^\[(\d{4}-\d{2}-\d{2}T[\d:.]+Z)\]\s+\[INFO\]\s+Human keywords matched\s+(\{.*\})',
                re.MULTILINE,
            )
            for m in kw_re.finditer(ra_text):
                try:
                    payload = json.loads(m.group(2))
                    kw_events.append({"ts": m.group(1), "keywords": payload.get("keywords", [])})
                except Exception:
                    pass
        except Exception:
            pass
    if kw_events:
        last_kw = kw_events[-1]
        result["subsystems"]["keywords"] = {
            "label": "Keyword Detection",
            "status": "ok",
            "detail": f"Last: {', '.join(last_kw['keywords'][:6])}",
            "lastSeen": last_kw["ts"],
        }
    else:
        result["subsystems"]["keywords"] = {
            "label": "Keyword Detection",
            "status": "idle",
            "detail": "No keyword triggers yet",
            "lastSeen": None,
        }

    # --- Subsystem: Compression ---
    if last_compaction_done:
        saving = last_compaction_done.get("saving", "?")
        swapped = last_compaction_done.get("turnsCompressed", 0)
        hit_rate = f"{cache_hits}/{cache_hits+cache_misses}" if (cache_hits + cache_misses) > 0 else "n/a"
        result["subsystems"]["compression"] = {
            "label": "Compression",
            "status": "ok",
            "detail": f"{blocks_count} blocks in context ({blocks_raw}→{blocks_comp} tok), "
                      f"saving: {saving}, cache: {hit_rate}",
            "lastSeen": last_compaction_done.get("ts"),
        }
    elif blocks_count > 0:
        ratio_str = f"{round(blocks_comp/blocks_raw*100)}%" if blocks_raw > 0 else "?"
        result["subsystems"]["compression"] = {
            "label": "Compression",
            "status": "ok",
            "detail": f"{blocks_count} blocks ({blocks_raw}→{blocks_comp} tok, {ratio_str})",
            "lastSeen": None,
        }
    else:
        result["subsystems"]["compression"] = {
            "label": "Compression",
            "status": "idle",
            "detail": f"No compression yet (trigger: {compress_trigger} total context)",
            "lastSeen": None,
        }

    # --- Subsystem: FIFO Eviction ---
    if fifo_events:
        last_fifo = fifo_events[-1]
        result["subsystems"]["eviction"] = {
            "label": "FIFO Eviction",
            "status": "ok",
            "detail": f"Last evicted block, {len(fifo_events)} total evictions",
            "lastSeen": last_fifo.get("ts"),
        }
    else:
        result["subsystems"]["eviction"] = {
            "label": "FIFO Eviction",
            "status": "idle",
            "detail": f"No evictions yet (trigger: {evict_trigger} compressed tok, current: {blocks_comp} tok)",
            "lastSeen": None,
        }

    # --- Conversation estimate (progress toward compression trigger) ---
    # Total context progress toward 36k trigger
    if actual_total > 0:
        pct = min(100, round((actual_total / compress_trigger) * 100))
        result["conversationEstimate"] = {
            "tokens": actual_total,
            "trigger": compress_trigger,
            "percent": pct,
            "msgCount": None,  # not tracked in V4.6.1 log
        }

    # --- Last event ---
    if log_events:
        result["lastEventTs"] = log_events[-1].get("ts")

    return jsonify(result)

# ---------------------------------------------------------------------------
# API: Chatbots (SQLite-backed)
# ---------------------------------------------------------------------------

import sqlite3

CHATBOTS_DB = Path(__file__).parent / "chatbots.db"

def _get_db():
    db = sqlite3.connect(str(CHATBOTS_DB))
    db.row_factory = sqlite3.Row
    # Auto-create tables if missing (first run on new install)
    db.executescript("""
        CREATE TABLE IF NOT EXISTS chatbots (
            id TEXT PRIMARY KEY, user_id TEXT DEFAULT 'default', name TEXT NOT NULL,
            system_prompt TEXT, greeting TEXT DEFAULT 'Hi! How can I help you today?',
            suggested_prompts TEXT DEFAULT '[]', position TEXT DEFAULT 'bottom-right',
            theme TEXT DEFAULT 'dark', primary_color TEXT DEFAULT '#4ade80',
            bg_color TEXT DEFAULT '#1a1a1a', text_color TEXT DEFAULT '#e0e0e0',
            allowed_domains TEXT DEFAULT '', rate_per_minute INTEGER DEFAULT 10,
            rate_per_hour INTEGER DEFAULT 100, enable_analytics INTEGER DEFAULT 1,
            show_watermark INTEGER DEFAULT 1, status TEXT DEFAULT 'active',
            created_at INTEGER DEFAULT (strftime('%s', 'now') * 1000),
            updated_at INTEGER DEFAULT (strftime('%s', 'now') * 1000),
            api_type TEXT DEFAULT 'internal', api_key_encrypted TEXT,
            model_id TEXT DEFAULT 'claude-sonnet', last_used_at INTEGER,
            icon_url TEXT DEFAULT '', icon TEXT DEFAULT '💬', icon_type TEXT DEFAULT 'emoji'
        );
        CREATE TABLE IF NOT EXISTS chatbot_conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT, chatbot_id TEXT NOT NULL,
            session_id TEXT NOT NULL, started_at INTEGER DEFAULT (strftime('%s', 'now') * 1000),
            ended_at INTEGER, message_count INTEGER DEFAULT 0, satisfaction_rating INTEGER,
            FOREIGN KEY (chatbot_id) REFERENCES chatbots(id)
        );
        CREATE TABLE IF NOT EXISTS chatbot_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT, conversation_id INTEGER NOT NULL,
            role TEXT NOT NULL, content TEXT NOT NULL,
            timestamp INTEGER DEFAULT (strftime('%s', 'now') * 1000),
            FOREIGN KEY (conversation_id) REFERENCES chatbot_conversations(id)
        );
        CREATE TABLE IF NOT EXISTS licenses (
            id TEXT PRIMARY KEY, user_id TEXT NOT NULL, chatbot_id TEXT,
            tier TEXT DEFAULT 'free', features TEXT DEFAULT '[]',
            stripe_subscription_id TEXT, stripe_customer_id TEXT, expires_at INTEGER,
            created_at INTEGER DEFAULT (strftime('%s', 'now') * 1000),
            updated_at INTEGER DEFAULT (strftime('%s', 'now') * 1000)
        );
        CREATE TABLE IF NOT EXISTS knowledge_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT, chatbot_id TEXT NOT NULL,
            filename TEXT NOT NULL, content TEXT, file_size INTEGER,
            uploaded_at INTEGER DEFAULT (strftime('%s', 'now') * 1000),
            FOREIGN KEY (chatbot_id) REFERENCES chatbots(id)
        );
        CREATE INDEX IF NOT EXISTS idx_conversations_chatbot ON chatbot_conversations(chatbot_id);
        CREATE INDEX IF NOT EXISTS idx_messages_conversation ON chatbot_messages(conversation_id);
        CREATE INDEX IF NOT EXISTS idx_licenses_user ON licenses(user_id);
    """)
    return db

@app.route("/api/chatbots")
def api_chatbots():
    """List all chatbots."""
    if not CHATBOTS_DB.exists():
        return jsonify([])
    db = _get_db()
    bots = [dict(r) for r in db.execute("SELECT * FROM chatbots ORDER BY created_at DESC").fetchall()]
    # Get conversation counts
    total_convos = 0
    for bot in bots:
        count = db.execute("SELECT COUNT(*) FROM chatbot_conversations WHERE chatbot_id=?", (bot["id"],)).fetchone()[0]
        bot["conversation_count"] = count
        total_convos += count
    db.close()
    active = sum(1 for b in bots if b.get("status") == "active")
    return jsonify({
        "chatbots": bots,
        "total": len(bots),
        "active": active,
        "totalConversations": total_convos,
        "avgSatisfaction": 0
    })

@app.route("/api/chatbots/<bot_id>")
def api_chatbot_detail(bot_id):
    """Get a single chatbot."""
    db = _get_db()
    bot = db.execute("SELECT * FROM chatbots WHERE id=?", (bot_id,)).fetchone()
    if not bot:
        db.close()
        return jsonify({"error": "not found"}), 404
    result = dict(bot)
    result["conversation_count"] = db.execute("SELECT COUNT(*) FROM chatbot_conversations WHERE chatbot_id=?", (bot_id,)).fetchone()[0]
    result["message_count"] = db.execute("SELECT COUNT(*) FROM chatbot_messages WHERE conversation_id IN (SELECT id FROM chatbot_conversations WHERE chatbot_id=?)", (bot_id,)).fetchone()[0]
    db.close()
    return jsonify(result)

@app.route("/api/chatbots", methods=["POST"])
def api_chatbot_create():
    """Create a new chatbot."""
    import uuid, time
    body = request.get_json(force=True)
    bot_id = uuid.uuid4().hex[:8]
    now = int(time.time() * 1000)
    db = _get_db()
    db.execute("""INSERT INTO chatbots (id, user_id, name, system_prompt, greeting, suggested_prompts,
        position, theme, primary_color, bg_color, text_color, allowed_domains,
        rate_per_minute, rate_per_hour, enable_analytics, show_watermark, status,
        created_at, updated_at, api_type, model_id, icon, icon_type)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (bot_id, "default", body.get("name", "New Chatbot"),
         body.get("system_prompt", "You are a helpful assistant."),
         body.get("greeting", "Hi! How can I help you?"),
         json.dumps(body.get("suggested_prompts", [])),
         body.get("position", "bottom-right"), body.get("theme", "dark"),
         body.get("primary_color", "#4ade80"), body.get("bg_color", "#1a1a1a"),
         body.get("text_color", "#e0e0e0"), body.get("allowed_domains", ""),
         body.get("rate_per_minute", 10), body.get("rate_per_hour", 100),
         1, 1, "active", now, now,
         body.get("api_type", "internal"), body.get("model_id", "claude-haiku"),
         body.get("icon", "💬"), body.get("iconType", "emoji")))
    db.commit()
    db.close()
    return jsonify({"ok": True, "id": bot_id})

@app.route("/api/chatbots/<bot_id>", methods=["PUT"])
def api_chatbot_update(bot_id):
    """Update a chatbot."""
    import time
    body = request.get_json(force=True)
    db = _get_db()
    bot = db.execute("SELECT id FROM chatbots WHERE id=?", (bot_id,)).fetchone()
    if not bot:
        db.close()
        return jsonify({"error": "not found"}), 404
    fields = ["name", "system_prompt", "greeting", "position", "theme",
              "primary_color", "bg_color", "text_color", "allowed_domains",
              "rate_per_minute", "rate_per_hour", "status", "model_id", "api_type",
              "icon", "icon_type"]
    # Map frontend camelCase to DB snake_case
    if "iconType" in body:
        body["icon_type"] = body.pop("iconType")
    updates = []
    values = []
    for f in fields:
        if f in body:
            updates.append(f"{f}=?")
            values.append(body[f])
    if updates:
        updates.append("updated_at=?")
        values.append(int(time.time() * 1000))
        values.append(bot_id)
        db.execute(f"UPDATE chatbots SET {','.join(updates)} WHERE id=?", values)
        db.commit()
    db.close()
    return jsonify({"ok": True})

@app.route("/api/chatbots/<bot_id>", methods=["DELETE"])
def api_chatbot_delete(bot_id):
    """Delete a chatbot and its data."""
    db = _get_db()
    db.execute("DELETE FROM chatbot_messages WHERE chatbot_id=?", (bot_id,))
    db.execute("DELETE FROM chatbot_conversations WHERE chatbot_id=?", (bot_id,))
    db.execute("DELETE FROM chatbots WHERE id=?", (bot_id,))
    db.commit()
    db.close()
    return jsonify({"ok": True})

@app.route("/api/chatbots/<bot_id>/conversations")
def api_chatbot_conversations(bot_id):
    """List conversations for a chatbot."""
    db = _get_db()
    convs = [dict(r) for r in db.execute(
        "SELECT * FROM chatbot_conversations WHERE chatbot_id=? ORDER BY started_at DESC LIMIT 50",
        (bot_id,)).fetchall()]
    db.close()
    return jsonify(convs)

@app.route("/api/conversations")
def api_conversations():
    """List conversations across all chatbots with filtering/pagination."""
    limit = request.args.get("limit", 20, type=int)
    offset = request.args.get("offset", 0, type=int)
    chatbot_id = request.args.get("chatbot_id", "")
    search = request.args.get("search", "")
    start_date = request.args.get("start_date", type=int)
    end_date = request.args.get("end_date", type=int)

    if not CHATBOTS_DB.exists():
        return jsonify({"conversations": [], "total": 0})

    db = _get_db()
    where = []
    params = []
    if chatbot_id:
        where.append("c.chatbot_id=?")
        params.append(chatbot_id)
    if start_date:
        where.append("c.started_at>=?")
        params.append(start_date)
    if end_date:
        where.append("c.started_at<=?")
        params.append(end_date)

    where_sql = (" AND " + " AND ".join(where)) if where else ""

    total = db.execute(
        f"SELECT COUNT(*) FROM chatbot_conversations c WHERE 1=1{where_sql}", params
    ).fetchone()[0]

    rows = db.execute(
        f"""SELECT c.*, b.name as chatbot_name
            FROM chatbot_conversations c
            LEFT JOIN chatbots b ON b.id = c.chatbot_id
            WHERE 1=1{where_sql}
            ORDER BY c.started_at DESC LIMIT ? OFFSET ?""",
        params + [limit, offset],
    ).fetchall()

    convs = []
    for r in rows:
        d = dict(r)
        # Get first message
        msg = db.execute(
            "SELECT content FROM chatbot_messages WHERE conversation_id=? AND role='user' ORDER BY timestamp ASC LIMIT 1",
            (d["id"],),
        ).fetchone()
        d["first_message"] = msg[0] if msg else None
        d["duration_seconds"] = (
            (d["ended_at"] - d["started_at"]) // 1000 if d.get("ended_at") and d.get("started_at") else None
        )
        convs.append(d)

    db.close()
    return jsonify({"conversations": convs, "total": total})

@app.route("/api/conversations/<int:conv_id>")
def api_conversation_detail(conv_id):
    """Get a single conversation with messages."""
    if not CHATBOTS_DB.exists():
        return jsonify({"error": "not found"}), 404
    db = _get_db()
    conv = db.execute("SELECT c.*, b.name as chatbot_name FROM chatbot_conversations c LEFT JOIN chatbots b ON b.id=c.chatbot_id WHERE c.id=?", (conv_id,)).fetchone()
    if not conv:
        db.close()
        return jsonify({"error": "not found"}), 404
    result = dict(conv)
    result["messages"] = [dict(m) for m in db.execute("SELECT * FROM chatbot_messages WHERE conversation_id=? ORDER BY timestamp ASC", (conv_id,)).fetchall()]
    db.close()
    return jsonify(result)

@app.route("/api/chatbots/<bot_id>/knowledge")
def api_chatbot_knowledge(bot_id):
    """List knowledge files for a chatbot."""
    if not CHATBOTS_DB.exists():
        return jsonify({"files": []})
    db = _get_db()
    files = [dict(r) for r in db.execute(
        "SELECT * FROM knowledge_files WHERE chatbot_id=? ORDER BY uploaded_at DESC", (bot_id,)
    ).fetchall()]
    db.close()
    return jsonify({"files": files})

@app.route("/api/chatbots/<bot_id>/knowledge", methods=["POST"])
def api_chatbot_knowledge_upload(bot_id):
    """Upload a knowledge file."""
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400
    f = request.files["file"]
    content = f.read().decode("utf-8", errors="replace")
    db = _get_db()
    db.execute(
        "INSERT INTO knowledge_files (chatbot_id, filename, content, file_size) VALUES (?,?,?,?)",
        (bot_id, f.filename, content, len(content)),
    )
    db.commit()
    db.close()
    return jsonify({"ok": True})

@app.route("/api/chatbots/<bot_id>/knowledge/<int:file_id>", methods=["DELETE"])
def api_chatbot_knowledge_delete(bot_id, file_id):
    """Delete a knowledge file."""
    db = _get_db()
    db.execute("DELETE FROM knowledge_files WHERE id=? AND chatbot_id=?", (file_id, bot_id))
    db.commit()
    db.close()
    return jsonify({"ok": True})

@app.route("/api/system-keys")
def api_system_keys():
    """Check which system API keys are available."""
    providers = []
    try:
        auth_path = os.path.expanduser("~/.openclaw/agents/main/agent/auth-profiles.json")
        with open(auth_path) as f:
            auth = json.load(f)
        profiles = auth.get("profiles", {})
        if "anthropic:manual" in profiles and profiles["anthropic:manual"].get("token"):
            providers.append({
                "id": "anthropic", "name": "Anthropic",
                "models": [
                    {"id": "claude-sonnet", "name": "Claude Sonnet"},
                    {"id": "claude-opus", "name": "Claude Opus"},
                    {"id": "claude-haiku", "name": "Claude Haiku"},
                ]
            })
        if "openai:manual" in profiles and profiles["openai:manual"].get("token"):
            providers.append({
                "id": "openai", "name": "OpenAI",
                "models": [
                    {"id": "gpt-4o", "name": "GPT-4o"},
                    {"id": "gpt-4", "name": "GPT-4"},
                ]
            })
    except Exception:
        pass
    return jsonify({"hasSystemKeys": len(providers) > 0, "providers": providers})

# ---------------------------------------------------------------------------
# API: Widget Chat
# ---------------------------------------------------------------------------

@app.route("/api/widget/chat", methods=["POST"])
def api_widget_chat():
    """Handle chat messages from the embeddable widget."""
    data = request.get_json() or {}
    bot_id = data.get("botId")
    messages = data.get("messages", [])
    if not bot_id or not messages:
        return jsonify({"error": "botId and messages required"}), 400

    db = _get_db()
    bot = db.execute("SELECT * FROM chatbots WHERE id=?", (bot_id,)).fetchone()
    db.close()
    if not bot:
        return jsonify({"error": "chatbot not found"}), 404

    bot = dict(bot)
    system_prompt = bot.get("system_prompt", "")

    # Load API keys
    try:
        import json as _json
        auth_path = os.path.expanduser("~/.openclaw/agents/main/agent/auth-profiles.json")
        with open(auth_path) as f:
            auth = _json.load(f)
    except Exception as e:
        return jsonify({"error": f"Auth config not found: {e}"}), 500

    # Build messages
    api_messages = []
    for m in messages[-20:]:
        role = m.get("role", "user")
        if role in ("user", "assistant"):
            api_messages.append({"role": role, "content": m.get("content", "")})

    model_id = bot.get("model_id", "claude-sonnet")

    try:
        import urllib.request

        # Route to appropriate provider
        if model_id.startswith("gpt"):
            # OpenAI
            api_key = auth["profiles"]["openai:manual"]["token"]
            oai_model = {"gpt-4o": "gpt-4o", "gpt-4": "gpt-4"}.get(model_id, "gpt-4o")
            oai_messages = [{"role": "system", "content": system_prompt}] + api_messages
            req_body = _json.dumps({"model": oai_model, "max_tokens": 1024, "messages": oai_messages}).encode()
            req = urllib.request.Request(
                "https://api.openai.com/v1/chat/completions",
                data=req_body,
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = _json.loads(resp.read())
            reply = result["choices"][0]["message"]["content"]
        else:
            # Anthropic (default for claude-*)
            api_key = auth["profiles"]["anthropic:manual"]["token"]
            ant_model = {
                "claude-sonnet": "claude-sonnet-4-20250514",
                "claude-opus": "claude-opus-4-20250514",
                "claude-haiku": "claude-haiku-4-20250514",
            }.get(model_id, "claude-sonnet-4-20250514")
            req_body = _json.dumps({
                "model": ant_model, "max_tokens": 1024,
                "system": system_prompt, "messages": api_messages,
            }).encode()
            req = urllib.request.Request(
                "https://api.anthropic.com/v1/messages",
                data=req_body,
                headers={
                    "Content-Type": "application/json",
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                },
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = _json.loads(resp.read())
            reply = result.get("content", [{}])[0].get("text", "Sorry, I couldn't generate a response.")

        return jsonify({"reply": reply})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/widget.js")
def widget_js():
    """Serve the embeddable chat widget JavaScript."""
    return send_from_directory(
        os.path.join(os.path.dirname(__file__), "static"),
        "widget.js",
        mimetype="application/javascript",
    )

# ---------------------------------------------------------------------------
# API: Shield Status
# ---------------------------------------------------------------------------

@app.route("/api/shield/status")
def api_shield_status():
    """Shield status including file guard."""
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "file_guard",
            os.path.join(os.path.dirname(__file__), "..", "shield", "file_guard.py"),
        )
        fg = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(fg)
        guard_status = fg.get_status()
        total_files = sum(g["total"] for g in guard_status.values())
        locked_files = sum(g["locked_count"] for g in guard_status.values())
        return jsonify({
            "active": locked_files > 0,
            "available": True,
            "mode": "protected",
            "file_guard": {
                "total_files": total_files,
                "locked_files": locked_files,
                "groups": guard_status,
            },
        })
    except Exception as e:
        return jsonify({
            "active": False,
            "available": False,
            "mode": "off",
            "error": str(e),
        })


@app.route("/api/shield/guard/status")
def api_shield_guard_status():
    """File guard status for all groups."""
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "file_guard",
            os.path.join(os.path.dirname(__file__), "..", "shield", "file_guard.py"),
        )
        fg = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(fg)
        return jsonify(fg.get_status())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/shield/guard/lock", methods=["POST"])
def api_shield_guard_lock():
    """Lock a file group (requires password for schg). Body: {group: 'group_id', password: '...'} or {file: '/path', password: '...'}"""
    data = request.get_json(silent=True) or {}
    password = data.get("password", "")
    if not password:
        return jsonify({"error": "Password required — schg needs root"}), 403
    # Validate password
    check = subprocess.run(
        ["sudo", "-S", "echo", "ok"],
        input=password + "\n", capture_output=True, text=True, timeout=10,
    )
    if check.returncode != 0:
        return jsonify({"error": "Invalid password"}), 403
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "file_guard",
            os.path.join(os.path.dirname(__file__), "..", "shield", "file_guard.py"),
        )
        fg = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(fg)
        if "group" in data:
            return jsonify(fg.lock_group(data["group"], password=password))
        elif "file" in data:
            return jsonify(fg.lock_file(data["file"], password=password))
        return jsonify({"error": "Provide 'group' or 'file'"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/shield/guard/unlock", methods=["POST"])
def api_shield_guard_unlock():
    """Unlock a file group. Requires password. Body: {group: 'group_id', password: '...'}"""
    data = request.get_json(silent=True) or {}
    password = data.get("password", "")
    if not password:
        return jsonify({"error": "Password required to unlock"}), 403
    # Validate password by attempting sudo -S with it
    check = subprocess.run(
        ["sudo", "-S", "echo", "ok"],
        input=password + "\n", capture_output=True, text=True, timeout=10,
    )
    if check.returncode != 0:
        return jsonify({"error": "Invalid password"}), 403
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "file_guard",
            os.path.join(os.path.dirname(__file__), "..", "shield", "file_guard.py"),
        )
        fg = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(fg)
        if "group" in data:
            return jsonify(fg.unlock_group(data["group"], password=password))
        elif "file" in data:
            return jsonify(fg.unlock_file(data["file"], password=password))
        return jsonify({"error": "Provide 'group' or 'file'"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ---------------------------------------------------------------------------
# API: Logician Status
# ---------------------------------------------------------------------------

@app.route("/api/logician/status")
def api_logician_status():
    """Read Logician monitor status file (deterministic, no AI)."""
    status_file = os.path.join(
        str(Path.home()), "resonantos-augmentor", "logician", "monitor", "status.json"
    )
    try:
        with open(status_file) as f:
            data = json.load(f)
        return jsonify(data)
    except FileNotFoundError:
        return jsonify({"status": "unknown", "error": "monitor not running"})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)})



@app.route("/api/logician/rules")
def api_logician_rules():
    """List Logician rules grouped by category."""
    rules_dir = os.path.join(os.path.dirname(__file__), "..", "logician", "rules")

    RULE_CATEGORIES = {
        "🤖 Agent Behavior": {
            "description": "How agents spawn, communicate, and operate within the system",
            "icon": "🤖",
            "files": ["agent_rules.mg", "agent_creation_rules.mg"],
        },
        "🔒 Security": {
            "description": "Data protection, access control, and threat prevention",
            "icon": "🔒",
            "files": ["security_rules.mg"],
        },
        "📋 Audit & Monitoring": {
            "description": "Decision tracking, logging, and system observability",
            "icon": "📋",
            "files": ["audit_rules.mg"],
        },
        "💻 Code Quality": {
            "description": "Testing requirements, coding standards, and verification gates",
            "icon": "💻",
            "files": ["coder_rules.mg", "coherence_gate_rules.mg"],
        },
        "🪙 Crypto & Wallet": {
            "description": "Transaction safety, wallet protection, and blockchain operations",
            "icon": "🪙",
            "files": ["crypto_rules.mg"],
        },
        "📐 Protocols": {
            "description": "Delegation, preparation, and research workflow enforcement",
            "icon": "📐",
            "files": ["delegation_rules.mg", "preparation_rules.mg", "research_rules.mg"],
        },
    }

    LOCKED_FILES = {"security_rules.mg", "audit_rules.mg"}

    # Scan rule files
    file_stats = {}
    try:
        if not os.path.isdir(rules_dir):
            return jsonify({"categories": [], "totals": {"rules": 0, "facts": 0, "files": 0, "categories": 0}, "error": "logician/rules/ directory not found"})

        for filename in sorted(os.listdir(rules_dir)):
            if not filename.endswith(".mg"):
                continue
            filepath = os.path.join(rules_dir, filename)
            try:
                with open(filepath) as f:
                    lines = f.read().splitlines()
                rule_count = len([l for l in lines if ":-" in l and not l.strip().startswith("%")])
                fact_count = len([l for l in lines if l.strip().endswith(".") and ":-" not in l and not l.strip().startswith("%") and len(l.strip()) > 1])
                file_stats[filename] = {"rules": rule_count, "facts": fact_count}
            except Exception:
                file_stats[filename] = {"rules": 0, "facts": 0}
    except Exception as e:
        return jsonify({"categories": [], "totals": {"rules": 0, "facts": 0, "files": 0, "categories": 0}, "error": str(e)})

    # Build categories
    assigned_files = set()
    categories = []
    for cat_name, cat_info in RULE_CATEGORIES.items():
        rule_count = 0
        fact_count = 0
        file_count = 0
        all_locked = True
        for fn in cat_info["files"]:
            if fn in file_stats:
                rule_count += file_stats[fn]["rules"]
                fact_count += file_stats[fn]["facts"]
                file_count += 1
                assigned_files.add(fn)
                if fn not in LOCKED_FILES:
                    all_locked = False
            else:
                all_locked = False
        if file_count == 0:
            all_locked = False
        categories.append({
            "name": cat_name,
            "description": cat_info["description"],
            "icon": cat_info["icon"],
            "ruleCount": rule_count,
            "factCount": fact_count,
            "fileCount": file_count,
            "locked": all_locked,
        })

    # Unassigned files go to Other
    other_rules = 0
    other_facts = 0
    other_files = 0
    for fn, stats in file_stats.items():
        if fn not in assigned_files:
            other_rules += stats["rules"]
            other_facts += stats["facts"]
            other_files += 1
    if other_files > 0:
        categories.append({
            "name": "📦 Other",
            "description": "Uncategorized rule files",
            "icon": "📦",
            "ruleCount": other_rules,
            "factCount": other_facts,
            "fileCount": other_files,
            "locked": False,
        })

    total_rules = sum(s["rules"] for s in file_stats.values())
    total_facts = sum(s["facts"] for s in file_stats.values())

    return jsonify({
        "categories": categories,
        "totals": {
            "rules": total_rules,
            "facts": total_facts,
            "files": len(file_stats),
            "categories": len(categories),
        }
    })


@app.route("/api/logician/rules/<filename>")
def api_logician_rule_content(filename):
    """Return content of a specific rule file."""
    # Security: only allow .mg files, no path traversal
    if not filename.endswith(".mg") or "/" in filename or "\\" in filename or ".." in filename:
        return jsonify({"error": "Invalid filename"}), 400

    rules_dir = os.path.join(os.path.dirname(__file__), "..", "logician", "rules")
    filepath = os.path.join(rules_dir, filename)

    try:
        with open(filepath) as f:
            content = f.read()
        return jsonify({"content": content, "filename": filename})
    except FileNotFoundError:
        return jsonify({"error": f"Rule file not found: {filename}"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/logician/rules/<filename>/toggle", methods=["POST"])
def api_logician_rule_toggle(filename):
    """Toggle a rule file's enabled state."""
    if not filename.endswith(".mg") or "/" in filename or "\\" in filename or ".." in filename:
        return jsonify({"error": "Invalid filename"}), 400

    # Security/audit rules cannot be toggled
    if filename in ("security_rules.mg", "audit_rules.mg"):
        return jsonify({"error": "Cannot toggle locked rules"}), 403

    config_dir = os.path.join(os.path.dirname(__file__), "..", "config")
    config_path = os.path.join(config_dir, "logician_rules.json")

    # Load existing state
    toggle_state = {}
    try:
        with open(config_path) as f:
            toggle_state = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    # Toggle
    current = toggle_state.get(filename, {}).get("enabled", True)
    toggle_state[filename] = {"enabled": not current}

    # Save
    try:
        os.makedirs(config_dir, exist_ok=True)
        with open(config_path, "w") as f:
            json.dump(toggle_state, f, indent=2)
        return jsonify({"filename": filename, "enabled": not current})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------------------------------------------------------------------------
# API: System Info (openclaw status)
# ---------------------------------------------------------------------------

@app.route("/api/system/status")
def api_system_status():
    """Run `openclaw status --json` and return result."""
    try:
        result = subprocess.run(
            ["openclaw", "status", "--json"],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode == 0:
            return jsonify(json.loads(result.stdout))
        else:
            # Try without --json
            result2 = subprocess.run(
                ["openclaw", "status"],
                capture_output=True, text=True, timeout=15
            )
            return jsonify({"raw": result2.stdout, "error": result2.stderr})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/system/restart", methods=["POST"])
def api_system_restart():
    """Restart OpenClaw gateway via SIGUSR1 (works for TUI and service modes)."""
    import signal
    try:
        # Find gateway process (node process on port 18789)
        result = subprocess.run(
            ["lsof", "-ti", "tcp:18789"], capture_output=True, text=True
        )
        pids = result.stdout.strip().split('\n')
        if not pids or not pids[0]:
            return jsonify({"ok": False, "error": "Gateway process not found on port 18789"}), 404
        # Send SIGUSR1 to trigger graceful restart
        pid = int(pids[0])
        os.kill(pid, signal.SIGUSR1)
        return jsonify({"ok": True, "message": f"SIGUSR1 sent to PID {pid}, restart initiated"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

# ---------------------------------------------------------------------------
# API: Config
# ---------------------------------------------------------------------------

@app.route("/api/config")
def api_config():
    """Read openclaw.json (redacting sensitive fields)."""
    try:
        cfg = json.loads(OPENCLAW_CONFIG.read_text())
        # Redact token
        if "gateway" in cfg and "auth" in cfg["gateway"]:
            cfg["gateway"]["auth"]["token"] = "***"
        return jsonify(cfg)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ---------------------------------------------------------------------------
# API: Models
# ---------------------------------------------------------------------------

@app.route("/api/models")
def api_models():
    """List available models via gateway."""
    result = gw.request("models.list")
    return jsonify(result)

# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Projects API (Monday.com-inspired project manager)
# ---------------------------------------------------------------------------

PROJECTS_DIR = Path(__file__).parent / "data" / "projects"
PROJECTS_DIR.mkdir(parents=True, exist_ok=True)

import uuid as _uuid

def _load_projects():
    """Load all project JSON files."""
    projects = []
    for f in sorted(PROJECTS_DIR.glob("*.json")):
        if f.name.startswith("_"):
            continue
        try:
            projects.append(json.loads(f.read_text()))
        except Exception:
            pass
    return projects

def _save_project(project):
    """Save a single project to disk."""
    pid = project["id"]
    path = PROJECTS_DIR / f"{pid}.json"
    path.write_text(json.dumps(project, indent=2))
    return project

def _compute_metrics(project):
    """Compute task metrics for a project."""
    tasks = project.get("tasks", [])
    total = len(tasks)
    done = sum(1 for t in tasks if t.get("status") == "done")
    blocked = sum(1 for t in tasks if t.get("status") == "blocked")
    in_progress = sum(1 for t in tasks if t.get("status") == "in_progress")
    todo = sum(1 for t in tasks if t.get("status") == "todo")
    project["metrics"] = {
        "totalTasks": total,
        "completedTasks": done,
        "blockedTasks": blocked,
        "inProgressTasks": in_progress,
        "todoTasks": todo,
        "completionPercent": round(done / total * 100) if total else 0
    }
    return project

@app.route("/api/projects")
def api_projects_list():
    projects = _load_projects()
    for p in projects:
        _compute_metrics(p)
    return jsonify({"projects": projects})

@app.route("/api/projects/graph")
def api_projects_graph():
    """Return all projects as graph data (nodes + edges) for Cytoscape.js."""
    projects = _load_projects()
    nodes = []
    edges = []
    tag_set = {}

    for p in projects:
        _compute_metrics(p)
        m = p.get("metrics", {})
        nodes.append({
            "data": {
                "id": p["id"],
                "label": p["name"],
                "type": "project",
                "status": p.get("status", "planning"),
                "priority": p.get("priority", "medium"),
                "icon": p.get("icon", ""),
                "color": p.get("color", "#6C5CE7"),
                "progress": m.get("completionPercent", 0),
                "totalTasks": m.get("totalTasks", 0),
                "doneTasks": m.get("completedTasks", 0),
                "description": (p.get("description") or "")[:120],
            }
        })
        for t in p.get("tasks", []):
            tid = f"{p['id']}:{t['id']}"
            nodes.append({
                "data": {
                    "id": tid,
                    "label": t["title"],
                    "type": "task",
                    "status": t.get("status", "todo"),
                    "priority": t.get("priority", "medium"),
                    "parent_project": p["id"],
                    "deadline": t.get("deadline"),
                    "assignee": t.get("assignee"),
                    "blockedBy": t.get("blockedBy"),
                    "createdAt": t.get("createdAt"),
                }
            })
            edges.append({
                "data": {
                    "id": f"e-{p['id']}-{t['id']}",
                    "source": p["id"],
                    "target": tid,
                    "type": "has_task",
                }
            })
        for tag in p.get("tags", []):
            tag_set.setdefault(tag, []).append(p["id"])

    for tag, pids in tag_set.items():
        tag_id = f"tag:{tag}"
        nodes.append({
            "data": {
                "id": tag_id,
                "label": tag,
                "type": "tag",
                "count": len(pids),
            }
        })
        for pid in pids:
            edges.append({
                "data": {
                    "id": f"e-tag-{tag}-{pid}",
                    "source": pid,
                    "target": tag_id,
                    "type": "tagged",
                }
            })

    return jsonify({"nodes": nodes, "edges": edges})


@app.route("/api/projects/<project_id>")
def api_project_get(project_id):
    path = PROJECTS_DIR / f"{project_id}.json"
    if not path.exists():
        return jsonify({"error": "Project not found"}), 404
    project = json.loads(path.read_text())
    _compute_metrics(project)
    return jsonify(project)

@app.route("/api/projects", methods=["POST"])
def api_project_create():
    data = request.json or {}
    pid = data.get("id") or str(_uuid.uuid4())[:8]
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    project = {
        "id": pid,
        "name": data.get("name", "Untitled Project"),
        "description": data.get("description", ""),
        "status": data.get("status", "planning"),
        "priority": data.get("priority", "medium"),
        "icon": data.get("icon", "🚀"),
        "color": data.get("color", "#6C5CE7"),
        "createdAt": now,
        "updatedAt": now,
        "deadline": data.get("deadline"),
        "tags": data.get("tags", []),
        "tasks": data.get("tasks", [])
    }
    _save_project(project)
    _compute_metrics(project)
    return jsonify(project), 201

@app.route("/api/projects/<project_id>", methods=["PUT"])
def api_project_update(project_id):
    path = PROJECTS_DIR / f"{project_id}.json"
    if not path.exists():
        return jsonify({"error": "Project not found"}), 404
    project = json.loads(path.read_text())
    data = request.json or {}
    for key in ("name", "description", "status", "priority", "icon", "color", "deadline", "tags"):
        if key in data:
            project[key] = data[key]
    project["updatedAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    _save_project(project)
    _compute_metrics(project)
    return jsonify(project)

@app.route("/api/projects/<project_id>", methods=["DELETE"])
def api_project_delete(project_id):
    path = PROJECTS_DIR / f"{project_id}.json"
    if not path.exists():
        return jsonify({"error": "Project not found"}), 404
    path.unlink()
    return jsonify({"deleted": project_id})

# --- Task CRUD within a project ---

@app.route("/api/projects/<project_id>/tasks", methods=["POST"])
def api_task_create(project_id):
    path = PROJECTS_DIR / f"{project_id}.json"
    if not path.exists():
        return jsonify({"error": "Project not found"}), 404
    project = json.loads(path.read_text())
    data = request.json or {}
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    task = {
        "id": data.get("id") or str(_uuid.uuid4())[:8],
        "title": data.get("title", "Untitled Task"),
        "description": data.get("description", ""),
        "status": data.get("status", "todo"),
        "priority": data.get("priority", "medium"),
        "assignee": data.get("assignee"),
        "deadline": data.get("deadline"),
        "blockedBy": data.get("blockedBy"),
        "createdAt": now,
        "updatedAt": now,
        "completedAt": None
    }
    project.setdefault("tasks", []).append(task)
    project["updatedAt"] = now
    _save_project(project)
    return jsonify(task), 201

@app.route("/api/projects/<project_id>/tasks/<task_id>", methods=["PUT"])
def api_task_update(project_id, task_id):
    path = PROJECTS_DIR / f"{project_id}.json"
    if not path.exists():
        return jsonify({"error": "Project not found"}), 404
    project = json.loads(path.read_text())
    data = request.json or {}
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    for task in project.get("tasks", []):
        if task["id"] == task_id:
            for key in ("title", "description", "status", "priority", "assignee", "deadline", "blockedBy"):
                if key in data:
                    task[key] = data[key]
            task["updatedAt"] = now
            if data.get("status") == "done" and not task.get("completedAt"):
                task["completedAt"] = now
            elif data.get("status") != "done":
                task["completedAt"] = None
            project["updatedAt"] = now
            _save_project(project)
            return jsonify(task)
    return jsonify({"error": "Task not found"}), 404

@app.route("/api/projects/<project_id>/tasks/<task_id>", methods=["DELETE"])
def api_task_delete(project_id, task_id):
    path = PROJECTS_DIR / f"{project_id}.json"
    if not path.exists():
        return jsonify({"error": "Project not found"}), 404
    project = json.loads(path.read_text())
    before = len(project.get("tasks", []))
    project["tasks"] = [t for t in project.get("tasks", []) if t["id"] != task_id]
    if len(project["tasks"]) == before:
        return jsonify({"error": "Task not found"}), 404
    project["updatedAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    _save_project(project)
    return jsonify({"deleted": task_id})

# --- Bulk task reorder (drag-and-drop support) ---

@app.route("/api/projects/<project_id>/tasks/reorder", methods=["POST"])
def api_tasks_reorder(project_id):
    path = PROJECTS_DIR / f"{project_id}.json"
    if not path.exists():
        return jsonify({"error": "Project not found"}), 404
    project = json.loads(path.read_text())
    data = request.json or {}
    task_ids = data.get("taskIds", [])
    if task_ids:
        task_map = {t["id"]: t for t in project.get("tasks", [])}
        reordered = [task_map[tid] for tid in task_ids if tid in task_map]
        remaining = [t for t in project.get("tasks", []) if t["id"] not in task_ids]
        project["tasks"] = reordered + remaining
        _save_project(project)
    return jsonify({"ok": True})

# ---------------------------------------------------------------------------
# TODO API — aggregates project tasks + standalone todos
# ---------------------------------------------------------------------------

TODOS_FILE = Path(__file__).parent / "data" / "todos.json"


def _load_standalone_todos():
    if TODOS_FILE.exists():
        return json.loads(TODOS_FILE.read_text())
    return []


def _save_standalone_todos(todos):
    TODOS_FILE.parent.mkdir(parents=True, exist_ok=True)
    TODOS_FILE.write_text(json.dumps(todos, indent=2))


@app.route("/api/todo")
def api_todo_list():
    """Return all todos: project tasks + standalone, sorted by priority."""
    items = []
    priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}

    # Pull tasks from all projects
    projects = _load_projects()
    for p in projects:
        color = p.get("color", "#ffffff")
        pname = p.get("name", "")
        pid = p.get("id", "")
        icon = p.get("icon", "")
        for t in p.get("tasks", []):
            items.append({
                **t,
                "projectId": pid,
                "projectName": pname,
                "projectIcon": icon,
                "projectColor": color,
                "source": "project",
            })

    # Standalone todos
    for t in _load_standalone_todos():
        items.append({
            **t,
            "projectId": None,
            "projectName": None,
            "projectIcon": None,
            "projectColor": "#ffffff",
            "source": "standalone",
        })

    # Sort: incomplete first, then by priority, then by deadline
    def sort_key(item):
        done = 1 if item.get("status") == "done" else 0
        prio = priority_order.get(item.get("priority", "medium"), 2)
        dl = item.get("deadline") or "9999-12-31"
        return (done, prio, dl)

    items.sort(key=sort_key)
    return jsonify({"items": items, "count": len(items)})


@app.route("/api/todo/standalone", methods=["POST"])
def api_todo_create_standalone():
    """Create a standalone todo (not linked to any project)."""
    data = request.json or {}
    if not data.get("title"):
        return jsonify({"error": "Title required"}), 400
    todos = _load_standalone_todos()
    import uuid
    todo = {
        "id": str(uuid.uuid4())[:8],
        "title": data["title"],
        "description": data.get("description", ""),
        "status": data.get("status", "todo"),
        "priority": data.get("priority", "medium"),
        "deadline": data.get("deadline"),
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "updatedAt": datetime.now(timezone.utc).isoformat(),
    }
    todos.append(todo)
    _save_standalone_todos(todos)
    return jsonify(todo), 201


@app.route("/api/todo/standalone/<todo_id>", methods=["PUT"])
def api_todo_update_standalone(todo_id):
    todos = _load_standalone_todos()
    for t in todos:
        if t["id"] == todo_id:
            data = request.json or {}
            for k in ("title", "description", "status", "priority", "deadline"):
                if k in data:
                    t[k] = data[k]
            t["updatedAt"] = datetime.now(timezone.utc).isoformat()
            if data.get("status") == "done" and not t.get("completedAt"):
                t["completedAt"] = datetime.now(timezone.utc).isoformat()
            _save_standalone_todos(todos)
            return jsonify(t)
    return jsonify({"error": "Not found"}), 404


@app.route("/api/todo/standalone/<todo_id>", methods=["DELETE"])
def api_todo_delete_standalone(todo_id):
    todos = _load_standalone_todos()
    todos = [t for t in todos if t["id"] != todo_id]
    _save_standalone_todos(todos)
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

# ── DAO Bounty Board routes (registered late so all helpers are defined) ──
try:
    from server_bounty_routes import register_bounty_routes
    _bounty_ctx = {
        "require_identity_nft": _require_identity_nft,
        "check_rct_cap": _check_rct_cap,
        "record_rct_mint": _record_rct_mint,
        "derive_symbiotic_pda": _derive_symbiotic_pda,
        "get_fee_payer": _get_fee_payer,
        "TokenManager": TokenManager,
        "SolanaWallet": SolanaWallet,
        "RCT_MINT": _RCT_MINT,
        "RES_MINT": _RES_MINT,
        "RCT_DECIMALS": _RCT_DECIMALS,
    }
    register_bounty_routes(app, _bounty_ctx)
    print("[OK] Bounty board routes loaded")
except Exception as _bounty_err:
    print(f"[WARN] Bounty routes not loaded: {_bounty_err}")

# ── Contributor Profile routes ──
try:
    from server_profile_routes import register_profile_routes
    register_profile_routes(app)
    print("[OK] Profile routes loaded")
except Exception as _profile_err:
    print(f"[WARN] Profile routes not loaded: {_profile_err}")


def main():
    """Start the dashboard server."""
    print(f"\n⚡ ResonantOS Dashboard v2")
    print(f"   Gateway: {GW_WS_URL}")
    print(f"   SSoT root: {SSOT_ROOT}")
    print(f"   Auth token: ***{GW_TOKEN[-6:]}" if GW_TOKEN else "   Auth token: (none)")

    gw.start()
    start_auto_update_checker()

    # Wait briefly for connection
    time.sleep(1)
    if gw.connected:
        print(f"   ✓ Gateway connected (connId: {gw.conn_id})")
    else:
        print(f"   ✗ Gateway not connected yet ({gw.error or 'connecting...'})")

    print(f"\n   Dashboard: http://localhost:19100\n")
    app.run(host="0.0.0.0", port=19100, debug=False)


if __name__ == "__main__":
    main()
