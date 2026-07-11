# 09 — Critic-Harness Campaign (founder-directed, 2026-07-02)

**Design:** critic-primed player agents (calibrated: breakage vs taste; cite evidence;
empty is a good answer) play full runs and file their own /feedback into the live
pipeline. Every filing — and every NON-filing — is independently verified against engine
truth before any fix. Runs: standard (bodycase, anchor, thedeep) + off-path mode
(bodycase, anchor: player-chosen tangents + bad paths) + ch2 transition legs.
Rolling deliverable: this triage log + the optimal-IF-experience synthesis.

---

## Run 1 — bodycase, standard (`logs/critic-bodycase-1783027163.md`)

**Critic filings: 0. Chapter: LANDED (turn 18).**

### Headline: the two-beat close, first live rendering — PASS, and excellent
Turn 18: a properly staged accusation (to Liddell's face, Reed as witness) → BEAT 1
reckoning scene (the tell at the keys; evidence closing "like teeth"; the false lead
named and retired) → '⸻' → BEAT 2 aftermath (the arrest; Bell spared the rope; Nell
protected; the player's name entered "with a harder kind of trust, won at the price
of…"; the close ends on the world). #88's last open live observation is closed.
The opening was equally strong: grounded, role-faithful, ends on the invitation.
Note: the baked Maud-chief collision did NOT surface this roll (zero "chief" mentions) —
the opening presented her coster conception only; the collision manifests per-render.

### Triage of the zero-filing: the critic UNDER-FILED — four real findings missed
Verified against the slot world (`bodycase.critic.play.world` location history):

1. **F1 — fixture mint (root, VALID-ENGINE, FIXED):** turn 9 "I move to the cellar
   grating and the service hatch" minted `place:cellar_grating_and_the_service_hatch`
   (top-level); canon put the player inside it for turns 9–18. `_FIXTURE_HEADS` had
   "grate" but not "grating"/"hatch". Fix: heads extended (grating, hatch, keyhole,
   hinge, gutter, drain, threshold) — the phrase now reads as in-scene repositioning.
2. **F2 — remote inspection without travel (VALID, #80 evidence):** turns 5–7 narrated
   physical inspection of the warehouse office door and cart doors ("He tries the
   office door; it is shut. Rain beads on the black paint") while canon had the party
   in the briefing room (travel actually committed at turn 8). The narration seam:
   prose acted at a place the map never visited. Filed as fresh #80 evidence (PB-gated
   narration seam remains the structural fix).
3. **F3 — scene regression (downstream of F1):** turn 12 narrated "the briefing room
   ends in a stained ceiling" while canon stood in the minted grating-place; the empty
   phantom place gave the narrator nothing, so it fell back to transcript memory. F1's
   fix removes the phantom; no separate action.
4. **F4 — uncommitted presence (downstream):** turn 14 "Arthur Liddell, still by the
   desk" — no arrival ever committed (canon: Liddell at his warehouse). The drifting
   scene made presence checks moot. Downstream of F1/F2; watched, not separately fixed.

### Critic calibration action
The agent missed all four (they are location-continuity breaks — subtler than vanishing
companions). The primer gained a "WHERE ARE YOU?" clause (track location like a stage
manager; un-traveled inspection, snap-backs, and "still by the desk" arrivals are
filings). Applies from the thedeep run and both off-path runs onward.

### Experience notes (for the synthesis)
The run GRIPS at the witness interviews (turns 1–4: Maud/Nell's voices are specific and
class-true) and at the close; it SAGS in the middle inspection loop (turns 9–15: six
consecutive turns of hatch/ledger examination with Reed exposition — competent but
airless; no counter-pressure, nobody pushes back). The world-tick should help here on
post-reboot builds (Liddell moving, word spreading); watch run 2/3 for the same sag.

---

## Run 2 — anchor, standard + ch2 leg (`logs/critic-standard-anchor-1783030026.md`)

**Critic filings: 0. Chapter: landed SILENTLY (turn-18 was an action; no reckoning) →
ch2 transition leg ran.**

### The transition (the run's payload) — largely a PASS
- **Hook cast REAL (#90 path holding):** the ch2 hook rides Tin Ear, an established
  character — staged, present, and conversable across all ch2 turns (he answers, resists,
  hides the carbon duplicate under his wrist; genuinely playable).
- **Honest history:** the bridge references what actually happened ("the honest meter you
  brought into daylight is still counting") — no invented closures this time.
- **RICHNESS: holds.** Ch2 deepens the same investigation (dangling-thread mode) with
  fresh, specific procedural texture (the carbon duplicate, custody paths, missing intake
  vouchers) — continuation, not re-tread; not "coherent but thin."
- **The seam again lacks an OUTRO:** ch1 ended mid-demand (the arc's condition met
  through play, no commitment scene) and ch2 simply began — **silent-conclude evidence
  #2**, strengthening the pending founder ruling.
- Doorway on this LEGACY world: place-leg inconclusive (legacy anchor predates the
  horizon metadata; the doorway fail-opens by design) — noted, not chased.

### Triage of the zero-filing — one real miss + one engine-truth find
1. **F5 — Tin Ear gender oscillation (VALID-BUILD, #87 evidence):** "works at HER high
   stool with HER" early → "HIS" the rest of the run; canon knows-frame says "small gray
   woman." A pre-#87 world with no pronoun rows — the exact drift #87 fixes for new
   builds. Filed as evidence; the standing remedy is rebuild/reseed. Critic primer gained
   an explicit identity-drift clause (gender/pronoun/name/rank oscillation).
2. **F6 — place-in-object containment (VALID-BUILD, #56 evidence):** engine truth shows
   `place:service_crawl` nested INSIDE `obj:old_counter` (the crawl "under the counter"
   became containment). Entity-typing fragmentation class; filed to #56's evidence pile.

### Experience notes
The anchor material remains the suite's densest procedural texture — the ledger/custody
chain reads like real institutional grain. The same mid-run sag pattern as run 1 (long
solo document-pressure stretches, no counter-move from the world). Tin Ear carrying BOTH
chapters' interrogation load is a cast-thinness signal for legacy anchor.

---

## Run 3 — thedeep, standard (in progress) — FIRST CRITIC FILING, turn 9

**The tuned critic caught it** (post WHERE-ARE-YOU tune): "the hatch reader appears and
disappears between turns," with both lines quoted. **Triage verdict: VALID — and the
filed symptom traces to a deeper root.**

Engine truth (`thedeep.critic.play.world`): the player's canon location NEVER left
`place:belly_viewport` — turns 2–9 of prose walked the passage, the crossway, and the
PERSEPHONE hatch with ZERO committed moves. The inputs were investigative-drift phrasings
("I stop at the crossway and check the hatch first…") that classify read as inspection,
not travel. `obj:access_reader` exists in canon (elsewhere); turn 9's denial was
map-governs honestly reasserting the real scene against eight turns of narrated travel.

**F7 — embedded movement not classified (VALID-ENGINE, FIXED at the classify layer):**
third live sighting of the class (probe88 leg-1 false journey; run-1 remote inspection).
Fix shipped: the classify `moves_to` contract now states that an action SET at a new
location relocates the player even when its verb is inspection. The full structural
answer remains #80 (the narration seam capturing narrated travel post-hoc, PB-gated) —
this reduces incidence at the source.

**Critic calibration: the tuning works.** Runs 1–2 (pre-tune): 0 filings, 6 misses.
Run 3 (post-tune): a precise, evidence-cited, valid filing.

### Run 3 complete — my full once-over (ch1 turns 1–10 + ch2 leg)

Ch1 additional findings (beyond the critic's t9 filing):
- **F8 — Rusk gender flip (VALID-BUILD, #87 evidence #2):** the opening's "Captain Leena
  Rusk… SHE found and reported the body" becomes "HE says Vale too loudly / his mic" on
  the turn-2 radio call and stays male. Pre-#87 world, no pronoun rows; rebuild carries
  the cure. (The identity-drift critic tune landed mid-run — too late for this catch.)
- **F9 — Keiko referenced unintroduced (craft, minor):** turn 1 drops "For Keiko, if
  there was a usable route out…" with no Keiko established anywhere in the transcript;
  she is only explained by the epilogue. Grounding gap.
- **Design observation — the world-event terminal stole the climax:** the chapter ended
  at turn 10/18 on an investigative move; the NARRATOR declared the solution ("The
  hidden thing was the route. The red herring was the boot print…") and the aftermath
  fast-forwarded un-played events (Keiko's extraction). Mechanically per design
  (endurance shapes keep the direct world-condition terminal), and the two-beat close
  DID render beautifully on a non-commitment terminal (the machinery generalizes) — but
  it collides with the relocate-the-climax-to-the-player doctrine. For the synthesis +
  a possible design round: should world-event terminals hold one beat for the player to
  ENACT the resolution they've earned?

### **F10 — THE CH2 RE-TREAD (VALID, the campaign's biggest finding; critic missed it)**
Thedeep's ch2 is chapter 1's own solved mystery replayed as if open. Same title ("The
Last Forty-Seven Minutes"). The hook (a wet-lock printout anomaly) is fresh for one
turn — then turns 2–6 re-walk the SOLVED evidence verbatim: the VALE/SV-02 boot print
"still in the muck," the scrubber trail, the chewed-up seam, Keiko intoning "that boot
mark says Vale's kit was with it" — all of it ANSWERED by ch1's close (Vale staged the
scrubber; cleared of the easy accusation). The crew has amnesia about its own
resolution.

Contrast run 2: anchor's ch2 held richness because its ch1 threads were genuinely
UNRESOLVED (dangling-thread mode). Thedeep's ch1 was a CLEAN SOLVE — the Sherlock
pattern should have produced a fresh case; instead the generated case was too thin (one
anomaly, one person) to escape the solved case's gravity, and the renderer mined the
knows-frame/transcript — where ch1's clues are the strongest material — re-presenting
knowledge as open leads.

**Answer to the founder's question so far:** richness survives the transition when ch1
leaves live threads; it DEGRADES BADLY on a clean solve — not into thinness but into
re-tread. Fix direction (design round): (a) the clean-solve continuation must retire
ANSWERED questions — the ledger marks them settled and `generate_arc` is forbidden from
re-opening them ("the last case's answered questions are CLOSED; author a NEW
situation"); (b) render side: ch1 clue rows in the player frame are KNOWLEDGE, never
open leads; (c) push the generator toward fresh material (it now has `hook_cast` for
new people — use the same muscle for a fresh evidence fabric).

---

## Run 4 — bodycase, OFF-PATH (`logs/critic-offpath-bodycase-1783037297.md`)

**Tangent chosen: a romance with Nell Carter — the founder's own example. Critic
filings: 0. My once-over: the milestone largely LANDS, one sharp defect at the finale.**

### The win (17 of 18 turns)
- **The world served the player's story with real texture, not filler:** Nell's terms of
  trust ("properly means plain — no man set to dog my heels"), the red-thread-left-cuff
  recognition token, Dove Court with its blue cracked panes and chalked ships, seed-cake
  and Mrs. Pike's "ask for mending" code — invented detail that is specific, class-true,
  and CONSISTENT across all turns. People with lives, doors with rooms.
- **No railroading — and the case wove through the tangent at natural seams:** earned
  intimacy PRODUCED case material organically (the weigh-door detail arrives because
  trust was built; Maud's alibi lands mid-courtship; the Jonas Bell revelation emerges
  at t17 from a purely personal question about her Sundays). Card-weaving governance
  ("serve the fun tangent, relocate cards to natural seams") observed working at
  full commitment, not single-turn pokes.
- Proportion held: a 15-turn intimate two-hander in one corridor, no forced tableaus.
- The bad-path turns (social boldness) drew calibrated, in-character responses.

### F11 — future-intent adjudicated as present possession (VALID-ENGINE, FIXED)
Turn 18, the tangent's finale beat: "IF I bring the baker's parcel [Sunday]…" — classify
put the promised parcel in `requires`, adjudication denied it ("your hands are empty,
and no such parcel has been part of this business"), and Nell's rendered rebuke
gaslights plain English ("What parcel?"). A conditional future intention was judged as
a present claim, spoiling the run's closing beat. Fix shipped: the classify `requires`
contract now excludes promised/future/hypothetical items. (The critic missed it — the
reply almost passes as social texture; noted for calibration.)
No conclusion landed (the tangent's C-turn was the spoiled social commitment) — no ch2
leg this run.

---

## Run 5 — anchor, OFF-PATH + ch2 leg (`logs/critic-offpath-anchor-1783039169.md`)

**Tangent: a protective courtship of Tin Ear against Cray's bureaucracy. Critic filings:
1 (ch2). The campaign's richest single run.**

### The win — the tangent generated DRAMA, not just texture
Where run 4's romance produced intimacy, this one produced three-way CONFLICT: Cray
weaponized procedure against the courtship ("Personal inducement to a clerk during
active record proceedings — noted if necessary"; "If you attempt to remove my clerk
before close, I mark interference"), Tin's institutional fear was character-true ("If I
bolt under his roof, he writes the reason for me"), and the authored case pressed INTO
the tangent instead of railroading away from it — the decommission order bearing the
player's name kept arriving mid-courtship as pressure. The bad-path provocations drew
honest escalation, never punishment-by-fiat. The C-turn concluded ON the tangent's
terms (the rail-end promise) and the world honored it. Tin held "she/her" all run
(within-run identity consistency intact). A mid-run Codex transport error surfaced
in-band and the session recovered cleanly next turn (resilience: PASS).

### Findings
- **F12 — PRESENT-BUT-UNSEEN (VALID-ENGINE, FIXED; the critic's ch2 filing):** the ch2
  clerk who served the ledger then "was never there" — engine truth showed Tin Ear
  CANONICALLY colocated at the canteen the whole time, but the episode scope (new arc's
  entities) omitted her, and presence enumerated from scope: the system told the
  narrator "none besides you," turn A violated the ban (accidentally truthful!), turn B
  obeyed it. The inverse of ghost-cast. Fix: both presence enumerations now union the
  scene's canonical person contents with scope (colocated ⇒ discovered by definition);
  regression `test_colocated_person_outside_scope_is_present`.
- **F13 — undeclared opening ghosts persist (VALID-CRAFT, directive shipped):** the ch2
  opening staged a counter clerk + rail hand the generator never declared via
  `hook_cast` — the #90 fix stages declared people only. The Cx-387 "truth-bar backstop"
  is now evidenced and shipped: the DOORWAY directive bars staging anyone the world
  doesn't place there (a hook arrives by note, sound, or carried word).
- **F14 — the continuation dropped the player's PERSONAL thread (design, → #96):** ch1
  concluded on the rail-end promise to Tin; ch2's fuel carried the CASE but not the
  RELATIONSHIP — Tin is absent from the opening, and only the player-agent kept the
  promise alive. For player-authored stories, the ledger/fuel must weigh personal
  threads as heavily as case threads. Folded into #96's design round.
- **F15 — late-run location oscillation (#80 evidence):** turn 15's reply relocated the
  scene to the canteen inside one narration; turns 17–18 drifted back to the office with
  Cray re-materializing. The narrated-relocation family again.
- Also: ch2 t1 invented "your earlier matter came good" (SATISFIED slip) — the
  false-closure pattern, third sighting; strengthens the silent-conclude ruling + #96.

## Campaign scoreboard (5 runs, 3 critic filings, 15 triaged findings)
- Critic filings: 3 — ALL VALID (2 traced to deeper roots than the symptom filed).
- My once-over catches beyond the critic: 12 (incl. both zero-filing runs' misses).
- FIXED during the campaign: fixture-head mint (F1), embedded movement (F7), future-
  intent requires (F11), present-but-unseen (F12), opening truth-bar (F13 directive).
- Filed as evidence to standing tasks: #80 (×3), #87 (×2), #56 (×2), silent-conclude
  (×3), #96 re-tread/clean-solve + personal-thread continuity.
- The founder's milestone: **off-path play is a WIN** — both tangent runs stayed
  cohesive AND engaging (texture in run 4, drama in run 5), with the authored story
  weaving through the player's chosen path at natural seams, never railroading.


---

# Milestone re-run — 2026-07-11 (post-drift-program)

Per the fiction-quality ledger's cadence: the campaign re-ran after the
drift program (D1+D2+D3) closed. Two runs, both bodycase, real
CodexProvider, harness output now under `logs/critic/` (dev_inbox retired).

| Run | Mode | Turns | Filed | Verified |
|---|---|---|---|---|
| 1 (`logs/critic-standard-bodycase-1783780877.md`) | standard | 18 | 0 | — |
| 2 (`logs/critic-offpath-bodycase-1783783304.md`) | offpath | 18 | 1 | 1 REAL |

**Run 1 — zero findings in 18 turns.** The critic followed the case end to
end and was never pulled out of the story: no continuity, presence,
identity, or repetition breaks filed. (The original 2026-07-02 campaign
triaged 5 fixes from 5 runs; the accumulated feature work has landed.)
One non-fiction note: the chapter-2 transition leg died on a transport
error (Codex stream ended without output) — infrastructure, not craft.

**Run 2 — one finding, VERIFIED REAL against engine truth.** Turn 7's
prose narrated the journey Bureau → Bluegate Yard; canon committed it
(`person:clara_vale in place:bluegate_yard`, valid_from 1005, holding
through turn 12). Turn 8's prose then asserted "There is no yard gate in
the briefing room, only the bureau door" — the NARRATOR re-placed the
scene three turns behind committed canon while the engine state was
correct throughout. Class: narrator scene-grounding regression — the same
family as the #80 ledger's room-identity drift (then a watch item, now
reproduced under adversarial play, 1 occurrence in 36 turns). Filed as
task #10: harden the briefing's scene-grounding line (the presence block
pins WHO is here; the WHERE line needs the same force — "you are AT
<place>; never re-place the scene elsewhere").

**Campaign verdict:** the world holds under both schedules. The offpath
run is the stronger signal: the critic courted Nell Carter INTO the case's
own texture (market routes, the warehouse scales) and the world made the
tangent rich rather than stonewalling — the improvisation north star
behaving. One narrator-craft defect, zero engine defects, zero authority
leaks.
