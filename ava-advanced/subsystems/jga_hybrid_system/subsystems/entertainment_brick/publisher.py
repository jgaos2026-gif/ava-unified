"""Publisher: gated hand-off of releases/announcements to outside services.

How "posting to Spotify" actually works: Spotify (and Apple Music, YouTube
Music, Amazon, Tidal, Deezer...) do not accept uploads from apps. Music reaches
them through a DISTRIBUTOR. So targets like "spotify" are reached through an
adapter that talks to a distributor; this module never pretends otherwise.

Adapters
- ExportAdapter: writes a delivery package (manifest + asset hashes) to a
  folder for manual upload to any distributor. Works offline, today.
- DistributorAdapter: calls a transport function YOU supply, written against
  your chosen distributor's real API/credentials. This module ships no
  distributor API client, holds no tokens, and was not tested against a live
  service (none is reachable from the build environment).
- Social/announcement posting uses the same gate and the same adapters
  (an "announcement" package carries your text for targets like "instagram").

The gate (same philosophy as bookings)
  PREPARED -> APPROVED (by the release's own artist) -> EXPORTED | SUBMITTED | FAILED
- Release must be distributor_ready() (valid ISRC/UPC etc.).
- Approval is bound to the package hash, including SHA-256 of every asset
  file. Change the release or swap a file after approval -> send refused.
- send() is DRY-RUN by default: validates everything, touches nothing.
- A job sends at most once. The job id is passed to the distributor as an
  idempotency key. Failures are recorded, never silently retried.
- "SUBMITTED" means handed to the distributor, not live on Spotify.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone

from core import GateError, _COUNTERS

DSP_TARGETS = {"spotify", "apple_music", "youtube_music", "amazon_music", "tidal", "deezer"}
SOCIAL_TARGETS = {"instagram", "facebook", "x", "tiktok", "youtube"}
ALL_TARGETS = DSP_TARGETS | SOCIAL_TARGETS

_COUNTERS.setdefault("pub", 0)


class PublishError(GateError):
    pass


def _now():
    return datetime.now(timezone.utc).isoformat()


def _file_sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def package_hash(package: dict) -> str:
    return hashlib.sha256(json.dumps(package, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class Adapter:
    name = "adapter"
    reaches: set = set()
    live_capable = False

    def deliver(self, job: "Job", package: dict, assets: dict) -> dict:
        raise NotImplementedError


class ExportAdapter(Adapter):
    """Offline hand-off: writes <out_dir>/<job id>/manifest.json."""
    name = "export"
    reaches = ALL_TARGETS
    live_capable = True          # writing a local folder is the live action

    def __init__(self, out_dir: str):
        self.out_dir = out_dir

    def deliver(self, job, package, assets):
        d = os.path.join(self.out_dir, job.id)
        os.makedirs(d, exist_ok=False)
        with open(os.path.join(d, "manifest.json"), "w") as f:
            json.dump({"job": job.id, "package_hash": job.package_hash, "package": package,
                       "asset_paths": assets}, f, indent=1, sort_keys=True)
        return {"external_id": d, "final_state": "EXPORTED"}


class DistributorAdapter(Adapter):
    """Wraps a transport(package, asset_paths) -> {"external_id": str} that YOU
    implement for your distributor. job.id is in the package as the idempotency key."""
    live_capable = True

    def __init__(self, name: str, transport, reaches=DSP_TARGETS, require_assets=("audio", "artwork")):
        if not callable(transport):
            raise PublishError("transport must be callable")
        self.name, self._transport = name, transport
        self.reaches, self.require_assets = set(reaches), tuple(require_assets)

    def deliver(self, job, package, assets):
        missing = [r for r in self.require_assets if r not in assets]
        if missing:
            raise PublishError(f"distributor delivery needs assets: {missing}")
        res = self._transport(package, dict(assets))
        if not isinstance(res, dict) or not res.get("external_id"):
            raise PublishError("transport must return {'external_id': ...}")
        return {"external_id": str(res["external_id"]), "final_state": "SUBMITTED"}


_ALLOWED = {("PREPARED", "APPROVED"), ("PREPARED", "CANCELLED"), ("APPROVED", "CANCELLED"),
            ("APPROVED", "EXPORTED"), ("APPROVED", "SUBMITTED"), ("APPROVED", "FAILED")}


class Job:
    def __init__(self, id, kind, release_id, adapter, targets, package, assets, artist_name):
        self.id, self.kind, self.release_id, self.adapter = id, kind, release_id, adapter
        self.targets, self.package, self.assets, self.artist_name = targets, package, assets, artist_name
        self.package_hash = package_hash(package)
        self.state, self.history, self.result = "PREPARED", [], None

    def _go(self, new, actor, note=""):
        if (self.state, new) not in _ALLOWED:
            raise PublishError(f"{self.id}: illegal transition {self.state} -> {new}")
        self.history.append({"from": self.state, "to": new, "actor": actor, "at": _now(), "note": note})
        self.state = new

    def to_dict(self):
        return {"id": self.id, "kind": self.kind, "release_id": self.release_id, "adapter": self.adapter,
                "targets": self.targets, "package": self.package, "assets": self.assets,
                "artist_name": self.artist_name, "package_hash": self.package_hash,
                "state": self.state, "history": self.history, "result": self.result}


class Publisher:
    def __init__(self, releases: dict, artists: dict):
        self._releases, self._artists = releases, artists
        self.adapters: dict[str, Adapter] = {}
        self.jobs: dict[str, Job] = {}

    def register(self, adapter: Adapter) -> None:
        self.adapters[adapter.name] = adapter

    def _owner(self, release):
        return next((a for a in self._artists.values() if a.name == release.artist), None)

    def _targets(self, adapter_name, targets):
        ad = self.adapters.get(adapter_name)
        if ad is None:
            raise PublishError(f"no adapter registered as {adapter_name!r}")
        targets = sorted(set(targets))
        if not targets or any(t not in ALL_TARGETS for t in targets):
            raise PublishError(f"targets must be a non-empty subset of {sorted(ALL_TARGETS)}")
        unreachable = [t for t in targets if t not in ad.reaches]
        if unreachable:
            raise PublishError(f"adapter {adapter_name!r} cannot reach {unreachable}; "
                               "DSPs such as Spotify are reached through a distributor adapter")
        return ad, targets

    def _hash_assets(self, assets):
        assets = dict(assets or {})
        for role, path in assets.items():
            if not isinstance(path, str) or not os.path.isfile(path):
                raise PublishError(f"asset {role!r} is not a readable file: {path!r}")
        return assets, {r: _file_sha256(p) for r, p in assets.items()}

    def prepare_release(self, release, adapter_name, targets, by, assets=None) -> Job:
        owner = self._owner(release)
        if owner is None or by is not owner:
            raise PublishError("only the release's own artist can prepare its publication")
        problems = release.problems()
        if problems:
            raise PublishError(f"release {release.id} is not distributor-ready: {problems}")
        ad, targets = self._targets(adapter_name, targets)
        assets, hashes = self._hash_assets(assets)
        package = {"kind": "release", "release": {k: v for k, v in release.to_dict().items()},
                   "targets": targets, "adapter": adapter_name, "asset_sha256": hashes}
        return self._add(Job(self._id(), "release", release.id, adapter_name, targets, package, assets, owner.name))

    def prepare_announcement(self, release, text, adapter_name, targets, by, assets=None) -> Job:
        owner = self._owner(release)
        if owner is None or by is not owner:
            raise PublishError("only the release's own artist can prepare its announcement")
        if not isinstance(text, str) or not text.strip():
            raise PublishError("announcement text required")
        ad, targets = self._targets(adapter_name, targets)
        assets, hashes = self._hash_assets(assets)
        package = {"kind": "announcement", "text": text.strip(), "release_id": release.id,
                   "targets": targets, "adapter": adapter_name, "asset_sha256": hashes}
        return self._add(Job(self._id(), "announcement", release.id, adapter_name, targets, package, assets, owner.name))

    def _id(self):
        _COUNTERS["pub"] += 1
        return f"pub-{_COUNTERS['pub']:03d}"

    def _add(self, job):
        self.jobs[job.id] = job
        return job

    def approve(self, job: Job, by) -> Job:
        owner = self._artists and next((a for a in self._artists.values() if a.name == job.artist_name), None)
        if by is not owner:
            raise PublishError(f"{job.id}: only the artist can approve their own publication")
        job._go("APPROVED", f"artist:{by.name}", note=f"approved package {job.package_hash[:12]}")
        return job

    def cancel(self, job: Job, by) -> Job:
        owner = next((a for a in self._artists.values() if a.name == job.artist_name), None)
        if by is not owner:
            raise PublishError(f"{job.id}: only the artist can cancel")
        job._go("CANCELLED", f"artist:{by.name}")
        return job

    def _recheck(self, job: Job):
        """Everything approved must still be true at send time."""
        if job.kind == "release":
            r = self._releases.get(job.release_id)
            if r is None or r.problems():
                raise PublishError(f"{job.id}: release no longer distributor-ready")
            if job.package["release"] != r.to_dict():
                raise PublishError(f"{job.id}: release changed after approval; prepare and approve again")
        _, hashes = self._hash_assets(job.assets)
        if hashes != job.package["asset_sha256"]:
            raise PublishError(f"{job.id}: an asset file changed after approval")
        if package_hash(job.package) != job.package_hash:
            raise PublishError(f"{job.id}: package no longer matches its approved hash")

    def send(self, job: Job, dry_run: bool = True) -> dict:
        if job.state != "APPROVED":
            raise PublishError(f"{job.id} is {job.state}; only APPROVED jobs can be sent")
        ad = self.adapters.get(job.adapter)
        if ad is None:
            raise PublishError(f"adapter {job.adapter!r} not registered in this session")
        self._recheck(job)
        if dry_run:
            return {"dry_run": True, "job": job.id, "would_deliver_to": job.targets,
                    "via": job.adapter, "package_hash": job.package_hash}
        if not ad.live_capable:
            raise PublishError(f"adapter {job.adapter!r} is not live-capable")
        try:
            res = ad.deliver(job, dict(job.package, idempotency_key=job.id), dict(job.assets))
        except Exception as e:                      # record, never retry silently
            job.result = {"error": f"{type(e).__name__}: {e}"}
            job._go("FAILED", "system", note=job.result["error"])
            raise PublishError(f"{job.id} failed: {job.result['error']}") from e
        job.result = {"external_id": res["external_id"]}
        job._go(res["final_state"], "system", note=f"via {job.adapter}")
        return {"dry_run": False, "job": job.id, "state": job.state, **job.result}

    # -- persistence --
    def load(self, rows: list) -> None:
        self.jobs.clear()
        for d in rows:
            if d["kind"] not in ("release", "announcement") or d["release_id"] not in self._releases:
                raise PublishError(f"stored job {d.get('id')} has bad kind or unknown release")
            j = Job(d["id"], d["kind"], d["release_id"], d["adapter"], d["targets"], d["package"],
                    d["assets"], d["artist_name"])
            if j.package_hash != d["package_hash"]:
                raise PublishError(f"stored job {j.id}: package hash mismatch")
            if not set(j.targets) <= ALL_TARGETS:
                raise PublishError(f"stored job {j.id}: bad targets")
            owner = next((a for a in self._artists.values() if a.name == j.artist_name), None)
            for h in d["history"]:
                if h["from"] != j.state or (h["from"], h["to"]) not in _ALLOWED:
                    raise PublishError(f"stored job {j.id}: illegal transition")
                want = {"APPROVED": f"artist:{j.artist_name}", "CANCELLED": f"artist:{j.artist_name}"}.get(h["to"], "system")
                if owner is None or h["actor"] != want:
                    raise PublishError(f"stored job {j.id}: {h['to']} by {h['actor']!r} not allowed")
                j.history.append(dict(h))
                j.state = h["to"]
            if j.state != d["state"]:
                raise PublishError(f"stored job {j.id}: state does not match history")
            j.result = d.get("result")
            self.jobs[j.id] = j
        top = max((int(i.split("-")[1]) for i in self.jobs), default=0)
        _COUNTERS["pub"] = max(_COUNTERS["pub"], top)
