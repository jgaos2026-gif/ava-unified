import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import money
from brick import Brick, StoreError
from publisher import DistributorAdapter, ExportAdapter, PublishError


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = self.tmp.name
        self.audio, self.art = os.path.join(t, "song.wav"), os.path.join(t, "cover.png")
        for p, c in ((self.audio, b"AUDIO"), (self.art, b"ART")):
            open(p, "wb").write(c)
        self.br = Brick()
        self.a = self.br.add_artist("A", "music")
        self.rel = self.br.add_release("Song", "A", metadata_complete=True, isrc="USRC17607839",
                                       upc="036000291452", artwork_ready=True)
        self.calls = []
        self.br.publisher.register(ExportAdapter(os.path.join(t, "out")))
        self.br.publisher.register(DistributorAdapter("fakedist", self.transport))
        self.pub = self.br.publisher
        self.assets = {"audio": self.audio, "artwork": self.art}

    def transport(self, package, assets):
        self.calls.append((package, assets))
        return {"external_id": "DIST-1"}

    def tearDown(self):
        self.tmp.cleanup()

    def job(self, adapter="fakedist", targets=("spotify",), assets=True):
        return self.pub.prepare_release(self.rel, adapter, targets, self.a, self.assets if assets else None)


class TestGate(Base):
    def test_cannot_send_before_approval_and_dry_run_default_touches_nothing(self):
        j = self.job()
        with self.assertRaises(PublishError):
            self.pub.send(j, dry_run=False)
        self.pub.approve(j, self.a)
        r = self.pub.send(j)                      # default = dry run
        self.assertTrue(r["dry_run"])
        self.assertEqual(self.calls, [])
        self.assertEqual(j.state, "APPROVED")

    def test_only_owner_prepares_approves_cancels(self):
        other = self.br.add_artist("B", "music")
        with self.assertRaises(PublishError):
            self.pub.prepare_release(self.rel, "fakedist", ["spotify"], other, self.assets)
        j = self.job()
        for bad in (other, "A", None):
            with self.assertRaises(PublishError):
                self.pub.approve(j, bad)
        with self.assertRaises(PublishError):
            self.pub.cancel(j, other)

    def test_not_ready_release_refused(self):
        r = self.br.add_release("Bad", "A")
        with self.assertRaises(PublishError):
            self.pub.prepare_release(r, "fakedist", ["spotify"], self.a, self.assets)

    def test_live_send_once_with_idempotency_key(self):
        j = self.job(); self.pub.approve(j, self.a)
        res = self.pub.send(j, dry_run=False)
        self.assertEqual((res["state"], res["external_id"]), ("SUBMITTED", "DIST-1"))
        self.assertEqual(self.calls[0][0]["idempotency_key"], j.id)
        with self.assertRaises(PublishError):
            self.pub.send(j, dry_run=False)         # no second send
        self.assertEqual(len(self.calls), 1)

    def test_release_edit_after_approval_blocks_send(self):
        j = self.job(); self.pub.approve(j, self.a)
        self.rel.title = "Song (remix)"
        with self.assertRaises(PublishError):
            self.pub.send(j, dry_run=False)
        self.assertEqual(self.calls, [])

    def test_asset_swap_after_approval_blocks_send(self):
        j = self.job(); self.pub.approve(j, self.a)
        open(self.audio, "wb").write(b"DIFFERENT")
        with self.assertRaises(PublishError):
            self.pub.send(j, dry_run=False)

    def test_release_becomes_unready_after_approval_blocks_send(self):
        j = self.job(); self.pub.approve(j, self.a)
        self.rel.isrc = "bad"
        with self.assertRaises(PublishError):
            self.pub.send(j)

    def test_spotify_not_reachable_by_plain_export_claim_but_export_is_manual_handoff(self):
        with self.assertRaises(PublishError):
            self.pub.prepare_release(self.rel, "fakedist", ["instagram"], self.a, self.assets)  # not a DSP route
        with self.assertRaises(PublishError):
            self.pub.prepare_release(self.rel, "fakedist", ["myspace"], self.a, self.assets)
        with self.assertRaises(PublishError):
            self.pub.prepare_release(self.rel, "nope", ["spotify"], self.a)

    def test_distributor_needs_audio_and_artwork_and_failure_is_recorded_not_retried(self):
        j = self.job(assets=False); self.pub.approve(j, self.a)
        with self.assertRaises(PublishError):
            self.pub.send(j, dry_run=False)
        self.assertEqual(j.state, "FAILED")
        with self.assertRaises(PublishError):
            self.pub.send(j, dry_run=False)         # FAILED is terminal
        self.assertEqual(self.calls, [])

    def test_transport_exception_marks_failed(self):
        def boom(p, a): raise RuntimeError("503")
        self.pub.register(DistributorAdapter("boomdist", boom))
        j = self.job("boomdist"); self.pub.approve(j, self.a)
        with self.assertRaises(PublishError):
            self.pub.send(j, dry_run=False)
        self.assertEqual(j.state, "FAILED")
        self.assertIn("503", j.result["error"])

    def test_cancelled_job_cannot_send(self):
        j = self.job(); self.pub.approve(j, self.a); self.pub.cancel(j, self.a)
        with self.assertRaises(PublishError):
            self.pub.send(j, dry_run=False)


class TestExportAndAnnouncement(Base):
    def test_export_writes_manifest_with_hashes(self):
        j = self.job("export", ["spotify", "apple_music"]); self.pub.approve(j, self.a)
        res = self.pub.send(j, dry_run=False)
        self.assertEqual(j.state, "EXPORTED")
        m = json.load(open(os.path.join(res["external_id"], "manifest.json")))
        self.assertEqual(m["package_hash"], j.package_hash)
        self.assertEqual(set(m["package"]["asset_sha256"]), {"audio", "artwork"})
        self.assertEqual(m["package"]["targets"], ["apple_music", "spotify"])

    def test_announcement_same_gate(self):
        j = self.pub.prepare_announcement(self.rel, "New single out Friday", "export", ["instagram"], self.a)
        with self.assertRaises(PublishError):
            self.pub.send(j, dry_run=False)
        with self.assertRaises(PublishError):
            self.pub.prepare_announcement(self.rel, "  ", "export", ["instagram"], self.a)
        self.pub.approve(j, self.a)
        self.pub.send(j, dry_run=False)
        self.assertEqual(j.state, "EXPORTED")


class TestPersistence(Base):
    def test_jobs_roundtrip_and_forgery_refused(self):
        j = self.job(); self.pub.approve(j, self.a)
        path = os.path.join(self.tmp.name, "b.json"); self.br.save(path)
        l = Brick.load(path)
        self.assertEqual(l.publisher.jobs[j.id].state, "APPROVED")
        self.assertEqual(l.publisher.jobs[j.id].package_hash, j.package_hash)
        self.assertEqual(l.publisher.adapters, {})   # adapters/transports are never persisted
        l.publisher.register(ExportAdapter(os.path.join(self.tmp.name, "out2")))
        nj = l.publisher.prepare_release(l.releases[self.rel.id], "export", ["spotify"], l.artists[self.a.artist_id])
        self.assertNotEqual(nj.id, j.id)
        def tamper(fn):
            doc = json.load(open(path)); fn(doc["publish_jobs"][0])
            doc = money.seal({k: v for k, v in doc.items() if k not in ("receipt_hash", "hash_mode")}, None)
            json.dump(doc, open(path, "w"))
        tamper(lambda d: d["history"][-1].update(actor="system"))    # approval not by artist
        with self.assertRaises(StoreError):
            Brick.load(path)
        self.br.save(path)
        tamper(lambda d: d["package"].update(targets=["tidal"]))      # package changed post-approval
        with self.assertRaises(StoreError):
            Brick.load(path)
        self.br.save(path)
        tamper(lambda d: (d["history"].clear(), d.update(state="SUBMITTED")))  # forged "sent"
        with self.assertRaises(StoreError):
            Brick.load(path)


if __name__ == "__main__":
    unittest.main()
