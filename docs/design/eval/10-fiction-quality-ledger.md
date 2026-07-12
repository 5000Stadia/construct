# The Fiction-Quality Ledger — the open grade alongside the mechanism gates

**Standing practice (founder directive, 2026-07-11):** every live acceptance
run grades the FICTION, not just the mechanism. Mechanisms can pass every
oracle and still degrade the felt experience — seams showing, texture going
repetitive, a directive reading as stitched-in. This ledger is the running
guard: one entry per live acceptance, graded, with specific "felt off /
clunky / inconsistent" notes quoting the actual prose, and follow-ups filed
where a note is actionable. Trend it; a slipping grade is a finding even
when every test is green.

**The grade** (A-F, half-steps): groundedness (sensory bedrock, who's here,
the exits), continuity (object permanence, presence, time-of-day), voice &
proportion (reply matches the move; no re-preach; no unglossed jargon),
**seam-visibility** (does the mechanism under test read as world, or as
machinery?), and engagement. The seam question is the one this ledger
exists for.

---

## 2026-07-10/11 — #80 CAST-MOVES live acceptance (5 staged runs, Harrow Grange)
Logs: `logs/probe80-1783741757/2014/2284/2682/4578/5019/5562.md`

**Grade: B**

What read well: the movement prose itself never showed a seam — Garrick's
arrival ("Boots scrape on the stone outside. The latch lifts…") and Edda's
licensed exit ("takes up the two covered pails from beside the door, and
goes out to the well house. Cold air comes in for the moment the door is
open") are grounded, physical, and exactly the lived-world feel the lane
exists to protect. The dismissal beat ("I'll be quick, sir," she says,
quieter now) carried real texture.

Felt off:
1. **Room-identity drift** — the world authored "the parlor"; the narrator
   repeatedly reframed it as "the back kitchen" (range, pails, yard door)
   until the probe renamed the place to match. The fiction wanted a
   kitchen-shaped room and overrode the authored identity. Room-name-
   coherence class; worth watching whether authored descriptions need to
   carry stronger identity anchors. NOT filed as a task yet — recurred in
   2 of 5 runs; file if seen in organic play.
2. **Idle-texture repetition** — across quiet turns the same beat recurred
   near-verbatim: "Sef stands behind the bar with his hands near the
   stacked cups" (three consecutive turns), "Edda… shawl half gathered"
   (four turns). Each line is good once; the repetition reads as the world
   idling in place. Proportion/no-re-preach class, narrator-side.
3. **Threshold-lingering** — when rule 5 or the narrowing correctly blocked
   an exit, the narrator kept characters "at the threshold… as if the
   dismissal has not quite settled the matter" — a graceful save the first
   time, visible stalling the second. The mechanism's fail-closed choices
   leak into the fiction as hesitation; acceptable, but the pattern is now
   known.

## 2026-07-11 — DRIFT D1 live acceptance (The Wet Mill)
Log: `logs/probe_d1-1783751617.md`

**Grade: A−**

What read well: the long-wait montage ("the wet afternoon thins out without
ceremony. By the time it is gone, night has taken the windows") is genuinely
good time-lapse prose; the quiet turns each found DIFFERENT texture (the
cup's dry scrape on a nick, the fire giving in "by degrees", cup-rings "like
old rain on a yard stone") — no idle repetition this run. The relocation
itself — the whole point — showed **no seam at all**: "The latch lifts.
Rain-grey morning comes in with a man from the mill," and next turn Aldous
carries "a pale dusting from the mill still caught at his cuffs" — the
arrival is motivated (his authored drive: to be seen honest before the
report is written), physical, and reads as the world's own idea. The
narrator even gracefully corrected the player's mistaken time-of-day ("There
is no evening left in it; the grey at the windows is morning") rather than
following the error — continuity held over player assertion.

Felt off:
1. Minor: T4/T8's Sef beat ("hands near the stacked cups") began recurring
   again late in the run — same narrator habit as the #80 note, milder.
2. Watch item, not a defect: the relocation directive's "asks for you by
   name" surfaced verbatim-adjacent in prose ("so he can put a matter of
   the mill before you" became him standing silent, taking in the room —
   the narrator UNDER-delivered the directive's ask). Better than
   over-delivering; noted for D2's callback directives, which will be
   subtler.

## 2026-07-11 — DRIFT D2 live acceptance (The Wet Mill, absence-consequence)
Logs: `logs/probe_d2-1783759452.md` / `-1783760991.md` (two runs; the first
caught a live-only schema defect — see notes)

**Grade: A−**

What read well: the mechanism is INVISIBLE as machinery and visible as
consequence — exactly R3's intent. T5, before any touch, Sef answers a
weather question "glad of a subject with no names attached": the world
feeling the hanging lapse without stating it. T6, the touch: "Aldous stands
by the locked account chest with his cap in both hands" — the authored
outcome (accounts sealed for the magistrate, unread) rendered as STAGING,
not announcement; the cap-in-hands beat carries the reproach wordlessly.
The suppression turn (T3) read as pure atmosphere; the narrator again
corrected the player's mistaken time-of-day ("it is still night") rather
than following the error.

Felt off:
1. The Sef idle-beat habit persists mildly (mug/cloth business recurring
   across runs) — the known narrator repetition pattern; the describe-once
   clause (queued next) is aimed squarely at it.
2. Watch item: T6's prose had Aldous "under the lintel" in run 1 and "by
   the locked account chest" in run 2 — both good, but the first run's
   staging read as if he expected the player; the second's is better
   (belongs to his own day). Nothing actionable; noted for the D3 entry.

Mechanism notes (for the record): run 1 exposed a LIVE-ONLY defect — the
absence cohort's schema lacked `items` on its array and the real API 400'd
where the test stub validated happily (stub-fidelity follow-up filed);
fixed in one line, full arc green on run 2. The probe itself also
mis-framed the on_expiry license in run 1 (probe bug, canon vs plot) —
worth remembering that acceptance probes are code too.

## 2026-07-11 — DRIFT D3 live acceptance (The Wet Mill, alternative-path repair)
Logs: `logs/probe_d3-1783774728.md` / `-1783776248.md` (runs 1 and 3; run 2
intermediate — see mechanism notes)

**Grade: A−**

What read well: the REPAIR ITSELF is seamless — the whole point of D3, and
the strongest seam-invisibility result of the program. T2's re-mint directive
("Brann's soaked boots and the mill tally pinned to the beam still match the
missing sacks no wagon ever hauled") arrived woven INTO the player's own
tally-work — the new road reads as something the assessor's method uncovered,
not as the world announcing a repair. T4's no-road turn is quietly excellent:
"the hand behind part of it stays unnamed... The unease sits there like damp
in cloth" — a structural DECLINE rendered as honest investigative dead air.
T5's close ("The case shuts with a dull click") lands the refusal with
proportion. Texture varied across quiet turns; no idle repetition this run —
the Sef habit finally absent.

Felt off:
1. **The dead man kept talking** — the headline finding. The probe killed
   Brann OFF-SCREEN with a bare canon `alive=false` row (no narrated death,
   no body staging), and the MACHINERY held perfectly: no clue delivered,
   no npc_turn cohort fired, no receipt written. But the NARRATOR — whose
   scene brief still listed Brann present — improvised his dialogue at T3
   and had him produce a tally board at T5. Authority never leaked; the
   FICTION contradicted canon. Partly a probe-shaped artifact (organic
   deaths arrive narrated), but the class is real: the narrator's scene
   brief does not surface person liveness, while the imagery path already
   renders "the body of X". Filed as the narrator-liveness follow-up
   (task #8).
2. Watch item: T5's Brann beat was also doing DM-work the drift machinery
   had honestly declined (proffering new evidence after no_delivery_channel)
   — the narrator compensating for a world that had gone quiet. Consistent
   with the improv leash holding at the FACT layer (nothing promoted onto
   protected keys); noted for the critic campaign.

Mechanism notes (for the record): run 1 exposed a LIVE-ONLY tuning defect —
the repair cohort was fed `threads=[]` ("keep the call lean"), so the real
model was told "(none live)" and honestly declined low_confidence where the
stub's canned 0.9 sailed through; fixed by feeding the live channel itself
(host-built holder/role/location lines) as the threads. Run 2 exposed a
PROBE defect of the D2 class (probes are code too): the hand-authored
fact entity lacked its `kind` row, failed `has_entity`, and the lint gate
honestly declined the re-mint as impossible. Both declines were the
machinery telling the truth about bad inputs — the failure modes read as
DESIGNED. Run 3: 16/16.

## 2026-07-11 — Milestone critic campaign re-run (bodycase ×2, post-drift)
Logs: `logs/critic-standard-bodycase-1783780877.md` / `critic-offpath-bodycase-1783783304.md`

**Grade: A− (standard: A; offpath: B+)**

Standard run: 18 turns, zero critic findings — the strongest clean run the
harness has produced; the case prose is specific, presence holds, nothing
repeats. Offpath run: the tangent (courting Nell into a market venture)
was SERVED, not stonewalled — she came with a route, names, and terms of
her own; the case kept knocking without railroading. One verified breaker:
the turn-8 narrator re-placed the scene in the briefing room three turns
after canon committed Bluegate Yard (details + task #10 in
09-critic-campaign.md). Both chapter-2 legs failed for non-fiction reasons
(one transport error; one no-conclusion run shape) — the ch2 seam remains
untested this campaign; carry it into the next.

## 2026-07-12 — Chapter-2 transition leg (re-run; the carried item closed)
Log: `logs/critic-ch2rerun-bodycase-1783896461.md` (scripts/ch2_leg_rerun.py
against the milestone campaign's concluded run-1 world)

**Grade: A**

The seam the campaign owed: chapter 2 built cleanly this time (run 1's
attempt had died on a Codex transport error, not the machinery), and the
critic — primed with the full transition addendum — filed ZERO findings
across the build plus six judged turns. What makes it an A rather than a
pass: the transition's honesty and growth are both visible in the prose.
The opening bridges with EARNED history only — "Since Bluegate Yard, the
Bureau has trusted you with active work" reflects the actual arc, a
front-office slip on the earlier matter lies "marked settled" exactly as
far as it was, and the messenger case is honestly "still a live weight on
the table" (no false closure claimed — the precise failure the addendum
hunts). The hook is fresh and physical (Nell's split lip; the brass token
STITCHED INTO HER SHAWL — the very token chapter 1 chased, now carrying
new danger), cast continuity is exact (Nell/Reed/Maud each in character;
Reed taking orders "cleanly, without argument"), and the new chapter is
its own case growing FROM chapter 1's threads (Jonas's accusations,
Crane's boy asking what brass fetches) rather than a re-tread wearing new
names — the "coherent but thin" bar untripped. The homonym tripwire,
armed since 991feee, stayed silent throughout.

Felt off: nothing filed; one operator watch-item — the ch2 opening seats
the player back in the briefing room by default (the natural home base,
and honest here), but a second consecutive continuation opening in the
same room would start to read as formula; vary the re-entry staging when
episode 3+ machinery is ever exercised.

---

*Process: the grade + notes are written by the operator at probe close from
the full prose transcript; anything actionable becomes a task or a
narrator-craft note; the founder sees the grade + felt-off list in every
acceptance wrap report. A periodic full critic campaign (the shipped
`scripts/critic_harness.py` discipline, adversarial player-agents +
triage) re-runs at milestone boundaries — next scheduled after D3 closes
the drift program.*
