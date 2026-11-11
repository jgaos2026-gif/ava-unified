"""Signed scope tokens for AVA history access (services_stdlib/scope_tokens.py).

Finding 12 (adversarial audit, 2026-11-10): caller-declared scopes are
not authenticated identities. The history store's own docs admitted
there was no token system yet — any caller could declare any division
scope and write. This module adds the token system, honestly:

  * A scope token is `AVA1.<b64url(canonical payload)>.<b64url(signature)>`.
  * Payload (signed, canonical JSON, sorted keys): version, algorithm,
    subject, scopes, issued-at, expiry.
  * Two signature methods, both stdlib-only:
      - Ed25519, via the existing Stitch helpers in stitch_link.py
        (`cryptography` when installed, else the pure-Python RFC 8032
        fallback in ~/workspace/your_files/micro-spine/ed25519.py).
        Preferred when a signing key is provisioned.
      - HMAC-SHA256 with a server key from env/keyfile. The single-server
        fallback: one secret, env or a 0600 keyfile, never in the repo.
  * The gate verifies tokens; caller-declared scopes keep working but
    are reported as `declared-untrusted` in results. A presented token
    that does not verify is an identity-layer refusal — never a silent
    downgrade to declared scopes.

What this does NOT do (the honest boundary):
  * It authenticates the KEY HOLDER, not a human. Which key belongs to
    which caller — and which scopes that caller may hold — is the
    OPERATOR'S provisioning step, not done here. There is no user
    registry, no role table, no key-rotation service in this module.
  * Tokens are bearer credentials: anyone holding a valid token can use
    its scopes until expiry. Keep TTLs short (default 1 hour), never log
    a token, never put one in a file, a URL, or a report.
  * The pure-Python Ed25519 fallback is NOT constant-time (same caveat
    as stitch_link.py / micro-spine). It is correctness-checked against
    the RFC 8032 vectors, not hardened. Use `cryptography` when it is
    installed; stitch_link picks it up automatically.
  * No key is ever created, written, or stored by this module. The
    operator generates a key (see `genkey` / `genseed` below), stores it
    in the environment or a 0600 keyfile, and restarts the server. Key
    rotation = replace the key, restart. A server restart is required
    to pick up a new key.

Provisioning (operator's step):
  * HMAC:   `python -m services_stdlib.scope_tokens genkey`
            -> put the printed secret in AVA_SCOPE_HMAC_KEY, or in a
               0600 file named by AVA_SCOPE_HMAC_KEY_FILE.
  * Ed25519: `python -m services_stdlib.scope_tokens genseed`
            -> put the printed seed in AVA_SCOPE_SIGNING_KEY_FILE
               (base64 32-byte seed, same format as ava_identity.key),
               or AVA_SCOPE_SIGNING_KEY. Verifiers that do not hold the
               seed take the public key from AVA_SCOPE_VERIFY_KEY(_FILE).

Env vars read (each *_FILE wins over the bare var when both are set):
  AVA_SCOPE_SIGNING_KEY_FILE / AVA_SCOPE_SIGNING_KEY  (base64 Ed25519 seed)
  AVA_SCOPE_VERIFY_KEY_FILE  / AVA_SCOPE_VERIFY_KEY   (base64 raw Ed25519 pubkey)
  AVA_SCOPE_HMAC_KEY_FILE    / AVA_SCOPE_HMAC_KEY     (base64 or raw HMAC secret)

Round-3 strict mode (Finding A, adversarial audit 2026-11-10):
  AVA_REQUIRE_AUTHENTICATED_SCOPES=true turns OFF the "no token means
  caller-declared scopes" behaviour. DEFAULT IS OFF: with the variable
  unset (or anything but a truthy value) the store behaves exactly as
  before — a call with no token is accepted with its declared scopes
  and reported as `declared-untrusted`. With strict mode ON, a call
  with no token is REFUSED at the identity layer, exactly like a
  presented-but-invalid token: it is never downgraded to declared
  scopes. Strict mode also fails VISIBLY when no scope key is
  configured at all (see require_authenticated_scopes() /
  HistoryStore construction): an operator must never mistake a
  deployment that is operationally functional but unauthenticated
  for a secured one. Strict mode is env-driven so a deployment opts
  in explicitly; the default stays permissive for local development
  only, and that default is a deliberate, documented choice — not an
  accident. Truthy values: 1, true, yes, on (case-insensitive).

Round-3 token hardening (same audit):
  * Expiry boundary: a token is expired AT exp (now >= exp), not
    after it (the old check, now > exp, let a token verify in its
    expiry second).
  * Base64url decoding is STRICT: only the base64url alphabet
    [A-Za-z0-9_-], no padding, canonical re-encoding. The old
    decoder silently discarded characters outside the alphabet and
    accepted padding and non-canonical trailing bits.

Stdlib only. No new secrets in any repo.
"""
import base64
import binascii
import hashlib
import hmac as _hmac
import json
import os
import re
import secrets
import time

try:
    from services_stdlib import stitch_link as _stitch_link
except Exception:  # noqa: BLE001 - plain-import layout fallback
    try:
        import stitch_link as _stitch_link
    except Exception:  # noqa: BLE001 - Ed25519 unavailable, HMAC still works
        _stitch_link = None

# The six divisions. Must match history_store.DIVISIONS (the six BCT
# strands, AWAITING JOHN'S RULING). history_store passes its own list
# when it calls verify, so a drift here cannot widen the gate there.
DIVISIONS = (
    "EXECUTION",
    "MEMORY",
    "VERIFICATION",
    "EVIDENCE",
    "RECOVERY",
    "GOVERNANCE",
)

TOKEN_PREFIX = "AVA1"
TOKEN_VERSION = 1
DEFAULT_TTL_SECONDS = 3600
MAX_TTL_SECONDS = 86400
_IAT_SKEW_SECONDS = 60


class ScopeTokenError(Exception):
    """Token issue/verify failed. The message never contains a key or a token."""


def _b64url_e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


_B64URL_ALPHABET = re.compile(r"^[A-Za-z0-9_-]+$")


def _b64url_d(text: str) -> bytes:
    """STRICT base64url decode (round 3). Rejects anything that is not
    a canonical unpadded base64url string: characters outside
    [A-Za-z0-9_-] (the old decoder silently discarded them), any "="
    padding, a length that cannot occur (len % 4 == 1), and
    non-canonical trailing bits (the decoded bytes must re-encode to
    exactly the input). Raises ValueError on any of these."""
    if not isinstance(text, str) or not text:
        raise ValueError("empty base64url segment")
    if not _B64URL_ALPHABET.match(text):
        raise ValueError("base64url segment has characters outside "
                         "the base64url alphabet")
    if len(text) % 4 == 1:
        raise ValueError("base64url segment has an impossible length")
    raw = base64.b64decode(text.translate(str.maketrans("-_", "+/"))
                           + "=" * (-len(text) % 4), validate=True)
    if _b64url_e(raw) != text:
        raise ValueError("base64url segment is not canonically encoded")
    return raw


# -- strict mode (round 3, Finding A) ---------------------------------
ENV_REQUIRE_AUTHENTICATED_SCOPES = "AVA_REQUIRE_AUTHENTICATED_SCOPES"
_TRUTHY = ("1", "true", "yes", "on")


def require_authenticated_scopes() -> bool:
    """True when the deployment opts into authenticated-only scopes:
    AVA_REQUIRE_AUTHENTICATED_SCOPES set to a truthy value (1/true/
    yes/on, case-insensitive). DEFAULT FALSE — unset means the old
    behaviour (declared scopes accepted, reported declared-untrusted).
    The default is permissive for local development only; a production
    deployment turns this on explicitly."""
    return (os.environ.get(ENV_REQUIRE_AUTHENTICATED_SCOPES, "")
            .strip().lower() in _TRUTHY)


def _canonical(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def _ed_available() -> bool:
    return _stitch_link is not None


def _ed_pubkey(seed: bytes) -> bytes:
    if _stitch_link is None:
        raise ScopeTokenError("Ed25519 unavailable: stitch_link not loaded")
    return _stitch_link._ed_pubkey(seed)


def _ed_sign(seed: bytes, msg: bytes) -> bytes:
    if _stitch_link is None:
        raise ScopeTokenError("Ed25519 unavailable: stitch_link not loaded")
    return _stitch_link._ed_sign(seed, msg)


def _ed_verify(pub: bytes, msg: bytes, sig: bytes) -> bool:
    if _stitch_link is None:
        return False
    return _stitch_link._ed_verify(pub, msg, sig)


def generate_hmac_key() -> str:
    """Fresh random 32-byte HMAC secret, base64. Returned, never stored:
    the operator puts it in env / a 0600 keyfile."""
    return base64.b64encode(secrets.token_bytes(32)).decode("ascii")


def generate_ed25519_seed() -> bytes:
    """Fresh random 32-byte Ed25519 seed. Returned, never stored: the
    operator puts its base64 in AVA_SCOPE_SIGNING_KEY_FILE."""
    if _stitch_link is not None:
        return _stitch_link._ed_generate()
    return secrets.token_bytes(32)


def _read_key_value(env_file: str, env_var: str):
    """Read a key from a *_FILE path (preferred) or a bare env var.
    File content is stripped; a base64 value decodes to bytes, any other
    value is used as UTF-8. Returns bytes or None. Never logs the value."""
    path = (os.environ.get(env_file) or "").strip()
    if path:
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = f.read().strip()
        except OSError as e:
            raise ScopeTokenError("cannot read %s: %s" % (env_file, e))
        if not raw:
            return None
        try:
            return base64.b64decode(raw, validate=True)
        except (binascii.Error, ValueError):
            return raw.encode("utf-8")
    value = (os.environ.get(env_var) or "").strip()
    if not value:
        return None
    try:
        return base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError):
        return value.encode("utf-8")


class ScopeTokenAuthority:
    """Holds the keys that issue and verify scope tokens. Construct with
    explicit keys (tests, embedding) or from the environment
    (ScopeTokenAuthority.from_env()). Never writes a key anywhere."""

    def __init__(self, ed_seed=None, ed_pub=None, hmac_key=None):
        self.ed_seed = ed_seed
        self.ed_pub = ed_pub
        if self.ed_seed is not None and len(self.ed_seed) != 32:
            raise ScopeTokenError("Ed25519 seed must be 32 bytes")
        if self.ed_pub is not None and len(self.ed_pub) != 32:
            raise ScopeTokenError("Ed25519 public key must be 32 bytes")
        if self.ed_seed is not None and self.ed_pub is None:
            self.ed_pub = _ed_pubkey(self.ed_seed)
        self.hmac_key = hmac_key
        if self.hmac_key is not None and len(self.hmac_key) < 16:
            raise ScopeTokenError("HMAC key must be at least 16 bytes")

    @classmethod
    def from_env(cls):
        seed = _read_key_value("AVA_SCOPE_SIGNING_KEY_FILE",
                               "AVA_SCOPE_SIGNING_KEY")
        pub = _read_key_value("AVA_SCOPE_VERIFY_KEY_FILE",
                              "AVA_SCOPE_VERIFY_KEY")
        hmac_key = _read_key_value("AVA_SCOPE_HMAC_KEY_FILE",
                                   "AVA_SCOPE_HMAC_KEY")
        return cls(ed_seed=seed, ed_pub=pub, hmac_key=hmac_key)

    @property
    def can_issue(self) -> bool:
        return self.ed_seed is not None or self.hmac_key is not None

    @property
    def has_verifying_key(self) -> bool:
        """True when this authority can verify at least one token
        method (an Ed25519 public key, derived from a seed or given
        directly, or an HMAC key). Strict mode refuses to run without
        one — see resolve_scopes() / HistoryStore."""
        return self.ed_pub is not None or self.hmac_key is not None

    def issue(self, scopes, subject="ava", ttl_seconds=DEFAULT_TTL_SECONDS):
        """Issue a signed scope token. Ed25519 when a signing seed is
        configured, else HMAC. Raises ScopeTokenError when no signing
        key is configured or the scopes are not valid divisions."""
        if not isinstance(subject, str) or not subject.strip():
            raise ScopeTokenError("subject must be a non-empty string")
        if not isinstance(scopes, (list, tuple)) or not scopes:
            raise ScopeTokenError("scopes must be a non-empty list")
        clean = sorted({str(s) for s in scopes})
        unknown = [s for s in clean if s not in DIVISIONS]
        if unknown:
            raise ScopeTokenError("unknown scope(s): %s" % ", ".join(unknown))
        try:
            ttl = int(ttl_seconds)
        except (TypeError, ValueError):
            raise ScopeTokenError("ttl_seconds must be an integer")
        if ttl < 1 or ttl > MAX_TTL_SECONDS:
            raise ScopeTokenError("ttl_seconds must be 1..%d" % MAX_TTL_SECONDS)
        now = int(time.time())
        if self.ed_seed is not None:
            alg = "ed25519"
        elif self.hmac_key is not None:
            alg = "hmac"
        else:
            raise ScopeTokenError(
                "no signing key configured: set AVA_SCOPE_SIGNING_KEY_FILE "
                "or AVA_SCOPE_HMAC_KEY_FILE (operator provisioning step)")
        payload = {"v": TOKEN_VERSION, "alg": alg, "sub": subject,
                   "scopes": clean, "iat": now, "exp": now + ttl}
        body = _canonical(payload)
        if alg == "ed25519":
            sig = _ed_sign(self.ed_seed, body)
        else:
            sig = _hmac.new(self.hmac_key, body, hashlib.sha256).digest()
        return "%s.%s.%s" % (TOKEN_PREFIX, _b64url_e(body), _b64url_e(sig))

    def verify(self, token, allowed_scopes=None):
        """Verify a presented token. Returns a report dict; never raises,
        never trusts by default. `ok` True means the signature verified,
        the token is in date, and every scope is a known division."""
        allowed = tuple(allowed_scopes) if allowed_scopes else DIVISIONS

        def _bad(reason):
            return {"ok": False, "authenticated": False, "scopes": [],
                    "sub": None, "method": None, "error": reason}

        if not isinstance(token, str) or not token:
            return _bad("no token presented")
        parts = token.split(".")
        if len(parts) != 3 or parts[0] != TOKEN_PREFIX:
            return _bad("malformed token")
        try:
            body = _b64url_d(parts[1])
            sig = _b64url_d(parts[2])
            payload = json.loads(body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError, binascii.Error):
            return _bad("malformed token")
        if not isinstance(payload, dict) or payload.get("v") != TOKEN_VERSION:
            return _bad("unsupported token version")
        alg = payload.get("alg")
        if alg not in ("ed25519", "hmac"):
            return _bad("unsupported token algorithm")
        sub = payload.get("sub")
        scopes = payload.get("scopes")
        iat = payload.get("iat")
        exp = payload.get("exp")
        if not isinstance(sub, str) or not sub.strip():
            return _bad("token has no subject")
        if (not isinstance(scopes, list) or not scopes
                or any(not isinstance(s, str) for s in scopes)):
            return _bad("token has no scopes")
        unknown = [s for s in scopes if s not in allowed]
        if unknown:
            return _bad("token carries unknown scope(s): %s" % ", ".join(unknown))
        if not isinstance(iat, int) or not isinstance(exp, int):
            return _bad("token has no valid timestamps")
        now = int(time.time())
        if now >= exp:
            return _bad("token expired")
        if iat > now + _IAT_SKEW_SECONDS:
            return _bad("token not yet valid")
        # Signature over the RE-canonicalized payload: the signature
        # covers exactly the claims as parsed, nothing else.
        expected_body = _canonical(payload)
        if alg == "ed25519":
            if self.ed_pub is None:
                return _bad("no Ed25519 verifying key configured")
            if len(sig) != 64 or not _ed_verify(self.ed_pub, expected_body, sig):
                return _bad("Ed25519 signature does not verify")
        else:
            if self.hmac_key is None:
                return _bad("no HMAC verifying key configured")
            if len(sig) != 32:
                return _bad("HMAC signature does not verify")
            expect = _hmac.new(self.hmac_key, expected_body,
                               hashlib.sha256).digest()
            if not _hmac.compare_digest(expect, sig):
                return _bad("HMAC signature does not verify")
        return {"ok": True, "authenticated": True,
                "scopes": sorted(set(scopes)), "sub": sub, "method": alg,
                "error": None}


def issue_scope_token(scopes, subject="ava", ttl_seconds=DEFAULT_TTL_SECONDS,
                      authority=None):
    """Issue a token with an explicit authority, or one built from the
    environment when authority is None."""
    auth = authority or ScopeTokenAuthority.from_env()
    return auth.issue(scopes, subject=subject, ttl_seconds=ttl_seconds)


def verify_scope_token(token, authority=None, allowed_scopes=None):
    """Verify a token with an explicit authority, or one built from the
    environment when authority is None."""
    auth = authority or ScopeTokenAuthority.from_env()
    return auth.verify(token, allowed_scopes=allowed_scopes)


def resolve_scopes(scopes=None, scope_token=None, authority=None,
                   allowed_scopes=None, require_authenticated=None):
    """Resolve the effective scopes for one history call.
    Returns (effective_scopes, scope_trust, refusal):
      * token presented and valid -> (token scopes, "authenticated", None)
      * token presented and invalid -> (None, "invalid-token", refusal dict)
      * no token, default mode -> (declared scopes, "declared-untrusted", None)
      * no token, STRICT mode -> (None, "missing-token", refusal dict)
    A presented-but-invalid token is never silently downgraded to the
    declared scopes: that would hide a forgery attempt. In strict mode
    (AVA_REQUIRE_AUTHENTICATED_SCOPES=true, or require_authenticated
    True) a MISSING token is refused the same way — an unauthorized
    caller must not be able to simply omit the token and declare
    GOVERNANCE or EVIDENCE. In strict mode with no verifying key
    configured at all, every call is refused with a visible error
    naming the missing provisioning, so an operator never mistakes
    an unauthenticated deployment for a secured one."""
    if require_authenticated is None:
        require_authenticated = require_authenticated_scopes()
    if scope_token is None:
        if not require_authenticated:
            return scopes, "declared-untrusted", None
        return None, "missing-token", {
            "ok": False, "state": "REFUSED",
            "error": "authenticated scopes required "
                     "(AVA_REQUIRE_AUTHENTICATED_SCOPES=true) and no "
                     "scope token was presented",
            "scope_trust": "missing-token"}
    auth = authority or ScopeTokenAuthority.from_env()
    if require_authenticated and not auth.has_verifying_key:
        return None, "no-verifying-key", {
            "ok": False, "state": "REFUSED",
            "error": "authenticated scopes required but no scope "
                     "verifying key is configured: provision "
                     "AVA_SCOPE_SIGNING_KEY_FILE / AVA_SCOPE_VERIFY_KEY_FILE "
                     "or AVA_SCOPE_HMAC_KEY_FILE (see scope_tokens.py)",
            "scope_trust": "no-verifying-key"}
    report = verify_scope_token(scope_token, authority=auth,
                                allowed_scopes=allowed_scopes)
    if not report.get("ok"):
        return None, "invalid-token", {
            "ok": False, "state": "REFUSED",
            "error": "scope token refused: %s" % report.get("error"),
            "scope_trust": "invalid-token"}
    return list(report["scopes"]), "authenticated", None


def main(argv=None):
    """Provisioning aid for the operator. Prints a fresh key to stdout
    for the operator to store in env / a 0600 keyfile. Never writes a
    key to disk. Usage:
      python -m services_stdlib.scope_tokens genkey   (HMAC secret)
      python -m services_stdlib.scope_tokens genseed  (Ed25519 seed+pubkey)
    """
    import sys
    args = list(argv if argv is not None else sys.argv[1:])
    if not args:
        print("usage: scope_tokens genkey|genseed")
        return 2
    if args[0] == "genkey":
        print("AVA_SCOPE_HMAC_KEY=%s" % generate_hmac_key())
        print("Store it in the environment or a 0600 keyfile "
              "(AVA_SCOPE_HMAC_KEY_FILE), then restart the server.")
        return 0
    if args[0] == "genseed":
        seed = generate_ed25519_seed()
        print("AVA_SCOPE_SIGNING_KEY=%s"
              % base64.b64encode(seed).decode("ascii"))
        if _ed_available():
            print("AVA_SCOPE_VERIFY_KEY=%s"
                  % base64.b64encode(_ed_pubkey(seed)).decode("ascii"))
        print("Store the seed in a 0600 keyfile "
              "(AVA_SCOPE_SIGNING_KEY_FILE), then restart the server.")
        return 0
    print("unknown command: %s (genkey|genseed)" % args[0])
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
