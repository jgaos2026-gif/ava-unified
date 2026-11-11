"""End-to-end walkthrough. Run: python3 demo.py   (uses a temp dir; nothing leaves this machine)"""
import os, tempfile
from brick import Brick
from publisher import ExportAdapter

d = tempfile.mkdtemp()
br = Brick()
a = br.add_artist("Test Artist", "music", location="Peoria", rate_floor_cents=5000)
br.set_secretary(a.artist_id, "blunt", "Dee")
sec = br.secretary_for(a.artist_id)

b = br.offer(a.artist_id, "Venue", "Friday Set", 100000, "2026-12-05")
print(sec.decision_prompt(b).text, "\n")
b.to_draft().approve(a).confirm()
print(sec.confirmed(b).text, "\n")

e = br.record_cleared("tx-1001", 100000, "gig-pay-cleared", b.id)
br.pay_cut(e["id"], 4000, "Manager")
print(sec.payment(br.ledger, e["id"]).text, "\n")

audio, art = os.path.join(d, "song.wav"), os.path.join(d, "cover.png")
open(audio, "wb").write(b"x"); open(art, "wb").write(b"y")
r = br.add_release("First Song", "Test Artist", metadata_complete=True, isrc="USRC17607839",
                   upc="036000291452", artwork_ready=True)
br.publisher.register(ExportAdapter(os.path.join(d, "out")))
job = br.publisher.prepare_release(r, "export", ["spotify", "apple_music"], a, {"audio": audio, "artwork": art})
br.publisher.approve(job, a)
print("dry run:", br.publisher.send(job))
print("live   :", br.publisher.send(job, dry_run=False), job.state)

br.save(os.path.join(d, "brick.json"))
print("\n" + sec.brief(Brick.load(os.path.join(d, "brick.json"))).text)
