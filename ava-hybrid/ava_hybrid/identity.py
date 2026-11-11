"""Identity: bound to a self-held key, NOT to a machine or a model.

The language model is rented and swappable. The machine is replaceable.
What stays the same across a move is: identity_id + soul_seed + key.
The key file is carried by the owner (USB, vault) separately from the
capsule. A receiving machine can only verify a capsule if it holds the
key. No key, no admission -- never silent merge.
"""
import hashlib
import hmac
import json
import os


def _canon(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()


class Identity:
    def __init__(self, name: str, soul_seed, secret: bytes | None = None):
        self.name = name
        # Soul Seed: John's canon side is COMPASSION / DECENCY / LOVE only.
        # Other fork values are recorded, never silently merged.
        self.soul_seed = tuple(soul_seed)
        self._secret = secret or os.urandom(32)
        self.id = "AVA-" + hashlib.sha256(self._secret).hexdigest()[:16]

    def sign(self, data: bytes) -> str:
        return hmac.new(self._secret, data, hashlib.sha256).hexdigest()

    def verify(self, data: bytes, sig: str) -> bool:
        return hmac.compare_digest(self.sign(data), sig)

    def sign_obj(self, obj) -> str:
        return self.sign(_canon(obj))

    def verify_obj(self, obj, sig: str) -> bool:
        return self.verify(_canon(obj), sig)

    # Key transport: owner-carried, never inside the capsule.
    def export_key(self) -> dict:
        return {"identity_id": self.id, "name": self.name,
                "soul_seed": list(self.soul_seed),
                "secret_hex": self._secret.hex()}

    @classmethod
    def from_key(cls, key_dict: dict) -> "Identity":
        ident = cls(key_dict["name"], key_dict["soul_seed"],
                    secret=bytes.fromhex(key_dict["secret_hex"]))
        assert ident.id == key_dict["identity_id"], "key file does not match its id"
        return ident
