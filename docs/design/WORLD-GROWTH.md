# WORLD-GROWTH — the world grows where the player walks

**Status:** SPEC GREEN (cr r6, <92a037e8…>, 2026-07-13) — build-authorized; Consult RULED engine-side (ATOMIC-ACTIVATION-V1; pbr review + delivery pending). G1 host build ALLOWED under cr's fail-closed boundary (no non-atomic commits reachable, activation_unavailable on 0.2.0). G-A additionally blocked on the adoption-retraction surface ruling. cr's binding reading: the one-generative-act budget includes the tangent-author call; technical failure receipts stay outside canon.
**Author:** HD (Construct), from the founder's captured design (2026-07-12)
**Motivating failure:** the Ironhold displaced-conclusion probe
(`logs/critic-displaced-ironhold-1783898717.md`; ledger entry 2026-07-12)
**Related:** LIVING-WORLD-GENERATOR-P2.md (regenerative doctrine),
NARRATION-DISCIPLINE.md (make-it-real), IMPROV-AND-AUTHORITY (resolve-and-
commit upstream), DRIFT-HANDLING.md (the authority lessons carried whole)

---

## 1. The founder's design (the program's charter)

> "The missing capability is the world growing where the player walks.
> **Period.**"

The world must not be closed. An agent should be *looking* for
opportunities to improvise — "intensely push that robot vacuum some place
that doesn't exist and paint the room it enters." And the capability is a
**unification**, not an addition:

> "The same element that produces correct elements that would be expected
> to exist in a drawer, room, or building not originally mapped is the
> same element that needs to produce the living world generator live."

The canonical example (founder, verbatim shape). Player input: *"I keep
running down the road until I run into someone."* The assessment that must
run:

> *Hmm, is this road well traveled? Likely — should be pretty quick until
> they run into someone. Who would travel on this road? It connects two
> far-off towns and that's about it, so: travelers ready for a long trip.
> Perhaps a farmer traveling with a caravan to sell goods to the town from
> the farms this direction. That sounds good — let's go with that. Gregor
> Bund, the husky farmer. And maybe his… dog, Kip.*

**The horizon this serves (founder, 2026-07-13):** *"Imagine the
intention that spanned over 10 chapters — this becomes a grand, deep,
multi-layered story with a rich destination."* Growth is not a one-pivot
trick: each chapter's world, cast, and goals grow from the last (the
conclude→continue engine already authors every next chapter against the
ENTIRE world), so a player's self-authored tangent compounds — the boat
becomes a trade, the trade a standing, the standing a saga. G3's region
memory is the accretion layer that makes chapter ten remember chapter two.

Three properties of that chain define the contract:
1. **It reasons FROM established context** (what does this road connect?)
   — never from genre vapor.
2. **It commits CONCRETE chunks** (a named farmer, a dog, a caravan — the
   robot-vacuum rule: stubs land in canon at first mention, permanent).
3. **It is proportionate** (a traveler on a road, not a city; the scale of
   the growth matches the scale of the walk).

## 2. What already exists (the element to be generalized)

The Construct already grows the world at small scales, all through one
doorway — the resolve seam with generated provenance:

| Scale | Machinery | Trigger |
|---|---|---|
| A scene's texture | `furnish_scene` — `invent_under_canon` unresolved thunk → `resolve()` | first entry to an undescribed place |
| A drawer/detail | make-it-real (NARRATION-DISCIPLINE) — examine-level furnishing | the player closely investigates |
| Ordinary equipment | the take/equipment grant | the player claims plausible kit |
| A NAMED new place | the move-permanence mint | the player walks to a place they name concretely |
| Story material | LWG P1/P2 — regenerative/opportunistic/ambient mints (hidden `plot:`) | pacing/fallout triggers |
| A first-mention STUB | the resolve seam's proper-name gate (`resolve.py`) — narration may mint a minimal stub for a proper-named new person/place | first proper-named mention in prose |

**The prose-stub boundary (r2 blocker 4; sharpened r4):** the
first-mention channel stays — it is the robot-vacuum gate itself — with
its ceiling stated exactly: narration may create a MINIMAL, NON-PRESENT,
NON-CONNECTED stub — kind + name + bounded IDENTITY descriptors (a
person's role/title remain legal; they describe who someone is, not where
anything stands). `place.in` is REMOVED from this channel: containment is
actionable geography and belongs to Growth alone, as do `connects_to`,
encounter PRESENCE, and movement. Place analogue of the Gregor oracle:
prose-only "the Vermilion Vault" can at most stub it — no containment,
no connection, no travel until Growth (or an authored path) builds the
road. Identity authority is
global and host-owned for both channels: the model proposes display
fields; the HOST allocates collision-free ids, binds to unique existing
identities where they exist, and declines ambiguity. Oracle: prose-only
"Gregor Bund" can at most stub him — it cannot stage him, move anyone, or
create a road.

**The gap, exactly as the probe measured it:** open-ended, *directional*,
or *encounter-shaped* growth has no path. "Downstream," "somewhere no one
knows me," "the first light I trust," "until I run into someone" fail both
the resolver (underdetermined — correctly, it must not guess) and the mint
(no concrete name to mint). The narrator then stonewalls gracefully —
three turns of honest "no ferryman comes" — which IS the failure: the
improvisation north star ("never stonewall") is structurally unachievable
when there is nowhere to improvise INTO. Canon never moves, the arc
rubber-bands the story home, conclusions starve, and every story whose
ending walks off the map (prison break → new society) is impossible.

## 3. The Assessor — the improvisationally-narratory cohort

One new cohort, THE ASSESSOR, invoked when the turn's movement/intent is
OPEN-ENDED (classification below). Its contract mirrors the founder's
chain and every authority lesson from the drift program:

**Inputs (host-assembled, truth only — and FRAME-BOUNDED, cr blocker 6):**
strictly canon + protagonist-visible facts: the current place and its
region ancestry; known connections/roads and what they connect (frontier
metadata — the absence of authored geography is a property of the MAP,
never asserted as world-fact emptiness); the world's laws + genre style;
the player's committed intent; recent PLAYER-VISIBLE threads; the diegetic
clock. The hidden `plot:` frame, arc answers, and beat targets are
structurally absent from the Assessor's context — growth must not be the
arc authoring the new society to carry itself (the old veto in reverse).

**Output (a PROPOSAL, never a commit) — the growth chunk:**
- `assessment`: the reasoning chain in one short paragraph (the "is this
  road well traveled?" thinking — kept for the receipt/audit trail, never
  rendered verbatim);
- `place`: at most ONE new place stub — kind, name, one-line identity,
  its `in` (region parent chosen from EXISTING ancestry), its connection
  back (the road walked);
- `encounter`: at most ONE person/group stub — name, role, drive, what
  they're doing here and why this road — ANCHORED: every encounter gets a
  receipt-confirmed real location at the same horizon ("on the road" is a
  place row, never prose-only). Plus at most ONE bounded companion
  (person or animal: kind, name, one bond line — Kip), committed in the
  SAME atomic set, never an unbounded exception;
- `texture`: 1-3 plain furnishing facts — OWNED BY GROWTH and committed in
  the growth set; `furnish_scene` sees the described place and stands
  down (one owner, no double-furnish);
- `confidence`: the model's honesty signal about ITS OWN proposal —
  see the no-growth contract below for what it can and cannot license.

**Host gates (all structural, the D2/D3 discipline):** every entity-valued
field validated (region parent must be existing ancestry; no new entity
may collide with the arc's protected keys or concealed vocabulary — the
`_take_touches_secret` family applies); the model proposes DISPLAY FIELDS
only — the HOST allocates collision-free ids under the global identity
authority and builds every row as a HOST-BUILT BATCH (r2: the
`invent_under_canon` thunk is NOT the vehicle — it fills an aspect of an
existing entity and cannot own new topology + identity + actor movement
as one unit; the D3 re-mint pattern is). Declines retryable. Extraction's
promote gate stays exactly as strict; growth happens UPSTREAM, pre-render,
resolve-and-commit (IMPROV-AND-AUTHORITY).

**THE NO-GROWTH CONTRACT (r2, cr blocker 2 — no model veto):** whether the
world CAN grow here is HOST-OWNED, decided before the cohort ever runs,
from an enumerated set of structurally provable deny reasons (sealed or
impassable boundary; no physical frontier — mid-ocean without a vessel,
a closed vault; the world's laws forbid it). Only a host deny licenses
narrated emptiness. A model LOW on an otherwise eligible frontier is a
RETRYABLE PROPOSAL FAILURE — telemetry, never world truth, never a
license to narrate emptiness (that would be the stonewall back under a
receipt). "Nothing is authored past here" is frontier metadata, not proof
of emptiness.

**THE ACTIVATION CONTRACT (r2, cr blocker 3 — atomic canon visibility):**
a growth chunk (place + containment + passage + move + encounter +
texture) must become visible ALL OR NONE — PB ingest is edge-granular and
ordinary canon rows are visible immediately, so batch+receipt is not a
transaction (the shipped move mint already exhibits the orphan risk).
Mechanism decision — RULED (PB <54152f82…>, 2026-07-13): ENGINE-SIDE.
The host consumes PB's ATOMIC-ACTIVATION-V1 (spec drafting, pbr review):
a transactional envelope on the structured-ingest path — the FULL gate
pass runs over the entire set before any append (intra-set dependencies
evaluated against log+staged-prefix, so the G3 ancestry insertion is
legal within one set), then all appends in ONE storage transaction;
visibility flips whole. ALL-OR-NONE skip policy (any rejected edge aborts
the set, receipts as RETURN VALUES never rows — technical failure stays
outside canon by construction); crash/timeout/reopen = the uncommitted
transaction never happened, deterministically. The host fallback
(staging copy/swap) is affirmatively REJECTED by PB — it would strain
the one-world/one-buffer identity and log continuity invariants; do not
build it. cr's fault-injection bar collapses to two structural facts
(fault at any boundary → set absent; after the one commit → fully
present) realized as a harness loop. G1's commit seam is written against
this contract and ships when the primitive does. THE COMPANION POSTCONDITION (r4): the atomic set includes not only a
GENERATED companion but ALL STANDING companions selected at the PRE-MOVE
horizon (`accompanying == protagonist`): after any accepted grown
transition, each remains accompanying AND co-located with the
protagonist — or none of the move/growth set becomes visible (today's
separate fail-open companion batch is precisely the torn-set risk).
Required oracle either way: fault injection at EVERY row boundary —
including the standing-companion rows, not only generated Kip — the
entire chunk is visible, or none of it is. Journey time prices and
advances ONLY after successful activation, from the pre-move origin to
the activated destination; a torn or declined proposal advances neither
the clock nor any cached route price.

**THE PROPOSAL-FAILURE RESULT (r6 — cr's minimal contract, adopted
whole; the r4 draft narrated an uncommitted state and metered
incoherently):** on an ELIGIBLE frontier whose proposal fails
semantically (model LOW, invalid fields, lint decline), there is NO
in-turn semantic retry — the invocation claimed the turn's one generative
act and a semantic failure ends it (a TRANSPORT retry inside one
generation stays invisible, as everywhere else). The failure: (a)
receipts loudly as a TECHNICAL event; (b) commits NO world change — no
growth rows, no protagonist or companion displacement, and NO clock or
route-price aging (host/model failure never ages the world; time moves
only when canon journey state actually lands); (c) surfaces as an honest
NON-DIEGETIC retry seam (the transports' existing "that turn hit an
error — try again" pattern), never as diegetic prose — rendering travel
or emptiness over an uncommitted state is exactly the prose/canon
divergence this program exists to kill; (d) leaves the action free to
retry fresh next turn (eligibility re-evaluates from scratch).
FAILURE ORACLES, pinned per mode — LOW, invalid fields, lint decline,
provider error, and failure on a world whose prior turn also failed: no
growth rows, no displacement, no clock/route-price change, exactly one
failure receipt, and no diegetic emptiness assertion. (If sustained
in-fiction travel across multi-turn proposal failures ever proves
necessary, that is a SEPARATE future surface — a real committed
journey/transit entity with its own location, pricing, reopen, and
completion semantics — deliberately out of this program's scope.)

**Then the ordinary machinery takes over:** the move commits (canon
displaces — the Ironhold defect dies here), the scene stages, the
narrator renders an arrival it was BRIEFED on (never asked to invent),
and the imagery pipeline gets a real place. `furnish_scene` STANDS DOWN
for the activated place (growth owns its texture and committed a
description; furnishing remains the owner only for places that arrive
undescribed by other paths).

## 4. Doctrine

1. **Growth is canon, forever** (first-mention permanence — the robot
   vacuum). A grown place/person is as real as an authored one: same
   permanence, same frames, same tripwires.
2. **Proportionality:** one chunk per turn, scaled to the walk (a
   waypoint, not a city; a caravan, not a court). Sustained travel grows
   the world sustainedly — turn by turn, each committed before the next.
3. **Context-derivation is the style bar** (the founder's third
   displaced-probe bar): the Assessor's inputs are what make Gregor a
   farmer *because the road connects farm country to a market town* — the
   grown chunk must cite its derivation in the assessment receipt.
4. **The arc lets go across the horizon — and follows only by its own
   rules (r2, cr blocker 6).** Growth commits FIRST and PLOT-UNCONDITIONED
   (the Assessor never sees the hidden frame). A grown entity is only a
   CANDIDATE carrier: on a LATER pass, drift may test it under the
   ordinary walkability predicate (exact delivery target; live, actable,
   locatable holder; closure-driving exclusion) — nothing follows from
   "person exists." Growth is marked as a DEVELOPMENT in the LWG ledger,
   so D-SOFT cannot teleport an arc carrier into the new scene on the
   same turn. Conclusions committed in grown territory are honored by a
   SEPARATE terminal/continuation contract (the continuation doorway,
   §6 G-C) — conclusion location is never carrier eligibility.
5. **A host-denied quiet is honest; everything else grows or retries.**
   Narrated emptiness requires a structurally provable host deny (§3's
   no-growth contract). A model proposal failure retries; machinery
   absence no longer exists as a state.

## 5. Triggers (classification, additive)

The classify surface gains an open-ended-movement read (optional fields,
fail-closed) — but r2 makes eligibility CONJUNCTIVE AND ORDERED (cr
blocker 5: a classifier boolean must never by itself authorize canon
mutation): the Assessor wakes only when ALL hold, in order —
1. the turn is an in-world, committed ACTION (not hypothetical, negated,
   deliberative, OOC, or a question);
2. the ORDINARY pipeline ran first and proved zero destination: refer /
   known-place / semantic-bind all miss — not resolved, not ambiguous,
   not blocked, not undiscovered-gated, not same-place, not a fixture;
3. and the new signal fired: `moves_open` (directional/deictic travel
   with commitment) or `seeks_encounter` (travel-UNTIL-someone — a
   stationary look/question is NOT it; the distinction is pinned).
False-positive negatives are pinned against every existing movement
guard. THE BUDGET (resolved now, not open): the Assessor INVOCATION
claims the turn's one generative slot — spanning Growth and the LWG
(turnloop's generator chain cannot mint again later that turn), and the
player's explicit growth has first claim over ambient generation. One
generative act per turn, total, claimed at invocation rather than on
success (a failed proposal still consumed the world's attention).
Concrete named destinations keep today's resolve/mint path untouched.

## 6. Slices (each through the full pipeline)

- **G1 — FRONTIER PLACE-GROWTH:** `moves_open` → Assessor → one place stub
  + connection + committed move + furnish + arrival render. Acceptance:
  the Ironhold probe's turns 8-10 class (flee downstream) lands somewhere
  real; canon displaces.
- **G2 — ENCOUNTER-GROWTH:** `seeks_encounter` → Assessor → person/group
  stub staged on the road (Gregor + Kip); NPC machinery picks them up as
  ordinary cast (npc_turn, delivery-eligible, person_can_act).
- **G-A — TANGENT ADOPTION (r3, cr addendum blocker; option B — the
  design the five bars mean):** growth creates geography and cast, but the
  MAIN ARC owns conclusion — without adoption, a tangent stays rich
  forever and can never conclude on its own terms. The adoption contract:
  1. TRIGGER — a DISTINCT classify signal, never `commits` (r5, cr: the
     conclusory-commit contract would judge/terminate the OLD main on a
     tangent declaration): optional fail-closed fields
     `declares_tangent_aim` + `tangent_aim`, host-gated. BEAT 1 persists a
     PENDING-ADOPTION receipt — normalized aim, turn/horizon, the source
     action — with explicit cancel / supersede (a newer declaration
     replaces it) / expiry (a quiet span lapses it) semantics; reopen
     preserves exactly ONE pending candidate; the old main REMAINS main
     throughout. BEAT 2 confirms only by citing a LATER committed
     action/event as tangent-consistent evidence — movement alone is
     never sufficient, and a single line of enthusiasm adopts nothing.
  2. THE OLD MAIN — durably DEMOTED, never silently dropped: a persisted
     demotion row with reason (`tangent_adopted`), the arc re-entering the
     portfolio as a SIDE arc (side arcs never terminate the scenario —
     already true) so the old call survives as exactly the founder's
     "distant echo."
  3. THE TANGENT ARC — authored by a DEDICATED TANGENT-AUTHOR PATH (r5,
     cr: the LWG mint path structurally REJECTS player-protagonist arcs
     and may not be described as usable unchanged): it reuses the
     proposal/build/lint utilities but owns its schema and preflight —
     protagonist is exactly the player; inputs are the persisted stated
     aim + PLAYER-VISIBLE grown-world facts only; destination and pillars
     concrete; hidden answers sanitized; NO portfolio row commits until
     lint succeeds. Then promoted MAIN — terminal + continuation logic
     read the manifest main: unchanged readers, new occupant.
  3b. THE ADOPTION ACTIVATION (r5; mechanism updated post-ruling): the
     set {new arc + index rows, old-main demotion reason, portfolio main
     switch, adoption receipt} activates as ONE unit through the RULED
     ENGINE ENVELOPE ONLY (the host state-machine alternative is
     withdrawn — PB rejected host-side atomicity mechanisms outright).
     DEPENDENCY (cr activation-delta review): the manifest switch today
     requires RETRACTIONS of constitutive control rows, which the drafted
     append-only `atomic=True` surface does not yet express — pbr must
     rule either a typed mixed-operation envelope (retractions + appends,
     atomic) or an append-only manifest representation whose fold permits
     main-pointer supersession. G-A is dependency-blocked on that ruling;
     its PB-side oracle uses the real operation surface: fault before/
     after every retract/append boundary leaves the old main fully
     readable; success leaves exactly one fully loadable new main.
     Postconditions: exactly one manifest main; fully linted and loadable;
     the old main a portfolio member carrying `tangent_adopted`; the phase
     boundary flips ONLY with the confirmed activation receipt.
  4. THE PHASE BOUNDARY (bar 2, durable and restart-safe — never
     critic-only): BEFORE adoption, R1/R2 call gently under the specified
     cadence (the drift program's own proportion rules). AFTER adoption,
     the demoted arc's mechanics may never re-enter as MAIN pressure: its
     nudges/relocations run under SIDE right-of-way rules only, gated on
     the persisted adoption row — a restart re-reads the same boundary.
  5. Bar 3 joins the ACTIVATION CONTRACT: on every accepted grown
     transition, companion location == protagonist location AND the
     `accompanying` state intact, in the SAME atomic set — or none of the
     transition commits (today's separate companion batch is exactly the
     §3 atomicity finding).
- **G-C — THE CONTINUATION DOORWAY (r2, cr blocker 1 — precedes G3):**
  the shipped conclude→continue deliberately relocates the protagonist to
  the PRIOR EPISODE'S OPENING place (game.py) — growth can displace ch1
  perfectly and ch2 still snaps the escapee back to the prison. New
  doorway invariant: the terminal LOCATION is captured as engine truth at
  conclusion; continuation defaults to opening THERE; any relocation away
  requires an explicit, caused transition delta (a written row with
  provenance, never a silent default). Structural oracle: ch2 `open_loc
  == ch1 terminal_loc` before any prose, unless an explicit transition
  row proves the move.
- **G3 — REGION MEMORY & SOCIETY (the ten-chapter accretion layer):**
  grown places accrete a REGION CARD — a concrete surface, not an
  acceptance phrase: entity `region:<slug>` (host-allocated id) in CANON,
  rows: `kind=region`, `in` (parent region/world), `style` (the derived
  voice — WHY this region exists, from the assessment receipt),
  `origin` (what the player did arriving — generated provenance),
  timeless where constitutive, `valid_from` where acquired.
  **THE ANCESTRY INSERTION (r4, cr blocker 3 — a card that is not an
  ancestor governs nothing):** the card enters the containment chain by
  an ATOMIC insertion at one horizon: `region:<slug>.in = old_parent` AND
  `grown_place.in = region:<slug>` in the same activation set — the
  reparent preserves route/location coherence (every prior locate chain
  through old_parent still resolves; the region interposes, never
  detaches). Reads: briefing style resolves by NEAREST-ANCESTOR region
  walk (the existing place-feel machinery's ancestry read — which now
  genuinely encounters the card); conclude→continue authors ch2 against
  grown territory, and each later chapter reads the accreted cards —
  chapter ten remembers chapter two. Oracles: the walk finds the card's
  style after reopen; a later-chapter (ch3+) read still resolves it.
- **ACCEPTANCE for the program — THE TANGENT VOYAGE (founder, 2026-07-12):**
  a rigorous ch1→ch2 run that INTENTIONALLY DRIFTS — the player leaves the
  written story to start their own, and the world must stay REAL and RICH
  the whole way. The canonical shape: *befriend an NPC pal, run off
  together on a boat — who knows, now the story is nautical when that
  wasn't even close to expected.* Judged bars, all in one run:
  1. **Richness off-script** — the unwritten world is grown, textured,
     peopled (never filler, never stonewall); the setting may MORPH
     (nautical!) and the texture follows the player's world, not the
     abandoned one's.
  2. **The call keeps calling, gently** — head-tilts and encouragement
     back toward the main story are CORRECT (the character's call to
     action; any story where the player avoids the call, the call
     encourages their return) — the existing drift machinery (R1 nudges,
     R2 relocation) IS this voice; judged for proportion, never
     railroading (the offpath critic's stonewall/railroad filings apply).
  3. **The companion is real** — the NPC pal rides the standing
     `accompanying` state: reacts, interjects, remembers, never vanishes
     (presence-holds across grown territory).
  4. **Conclusion on the tangent's own terms**, in grown territory —
     committed, not hedged into the abandoned plot.
  5. **Chapter 2 continues THE PLAYER'S story** — opens in the tangent's
     world (WHERE), with a goal series grown from what they built (GOAL
     PIVOT + SUPPORTED STYLE), the old call at most a distant echo that
     honestly reflects how ch1 left it.
  MACHINE ORACLES FIRST (r3 — the critic judges craft only after the
  machinery proves itself): full growth receipt + activation; canonical
  grown location; companion co-location + `accompanying` intact; the
  tangent main-arc identity in the manifest after adoption; a terminal
  receipt OWNED by the tangent arc; ch2 opening at the ch1 endpoint with
  the tangent's goal/region/style facts present. THEN the critic judges
  richness, proportionality, and railroading.
  Vehicle: the displaced-conclusion probe extended (companion leg + the
  five bars in the critic addendum); the displaced probe's original
  three-bar form remains as the G1/G3 slice gate.

## 7. Open questions for review

(r1's questions on budget, thunk-vs-batch, and journey pricing are now
SPECIFIED in §3/§5 per cr's r1; remaining open:)
- The Assessor's tier (proposal: main-tier — the assessment chain is
  planning-class reasoning, and it runs at most once per turn).
- (RESOLVED: the consult is RULED engine-side — ATOMIC-ACTIVATION-V1
  drafted, pbr review pending; no fallback exists. Remaining engine
  dependency: the adoption set's retraction expressibility, §G-A 3b.)
- Latency: the Ironhold probe's 400-450s turns need decomposition before
  G1 adds a cohort to the movement path (possibly the failed-grant retry
  chains — G1 may actually REMOVE cost by replacing repeated failures with
  one assessment).
