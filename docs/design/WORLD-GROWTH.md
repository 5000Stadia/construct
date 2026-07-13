# WORLD-GROWTH — the world grows where the player walks

**Status:** SPEC — awaiting cr review (r1)
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

**Inputs (host-assembled, truth only):** the current place and its region
ancestry; known connections/roads and what they connect (or the explicit
absence — "nothing is authored past here"); the world's laws + genre
style; the player's committed intent (flee hard / wander / seek someone);
recent narrative threads; distance/time context from the diegetic clock.

**Output (a PROPOSAL, never a commit) — the growth chunk:**
- `assessment`: the reasoning chain in one short paragraph (the "is this
  road well traveled?" thinking — kept for the receipt/audit trail, never
  rendered verbatim);
- `place`: at most ONE new place stub — kind, name, one-line identity,
  its `in` (region parent chosen from EXISTING ancestry), its connection
  back (the road walked);
- `encounter`: at most ONE person/group stub — name, role, drive, what
  they're doing here and why this road (+ optional companion/animal — Kip
  rides free);
- `texture`: 1-3 plain furnishing facts;
- `confidence`: how honestly this growth fits here (LOW = the world offers
  nothing; the host then narrates honest emptiness — an *assessed* quiet
  is not a stonewall).

**Host gates (all structural, the D2/D3 discipline):** every entity-valued
field validated (region parent must be existing ancestry; no new entity
may collide with the arc's protected keys or concealed vocabulary — the
`_take_touches_secret` family applies); the model picks among host-shaped
options where options exist; the HOST builds every row (stubs with correct
kinds through the ordinary gate, `classify` on, generated provenance);
commits receipt-confirmed complete-set-or-decline; declines retryable.
The narrator never grows the world through prose — extraction's promote
gate stays exactly as strict; growth happens UPSTREAM, pre-render,
resolve-and-commit (IMPROV-AND-AUTHORITY).

**Then the ordinary machinery takes over:** the move commits (canon
displaces — the Ironhold defect dies here), the scene stages, `furnish_
scene` paints on entry, the narrator renders an arrival it was BRIEFED on
(never asked to invent), and the imagery pipeline gets a real place.

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
4. **The arc lets go across the horizon — and then follows.** Growth must
   not be vetoed by the story (that is the rubber-band failure), and the
   story must not die at the border: the drift machinery (D1 relocation,
   D3's walkability doctrine) already knows how to move mechanics through
   carriers — a grown encounter is a legal carrier. Conclusion machinery
   honors conclusions committed in grown territory (the displaced-probe
   contract).
5. **An assessed quiet is honest; a structural stonewall is not.** If the
   Assessor says LOW confidence (mid-ocean, sealed vault), the narrator
   renders true emptiness — but the assessment RAN, and the receipt shows
   the world considered growing. Refusal by policy, never by absence of
   machinery.

## 5. Triggers (classification, additive)

The classify surface gains an open-ended-movement read (like
`addresses_present`: optional field, fail-closed to today's behavior):
- `moves_open`: directional/deictic travel with commitment ("downstream",
  "away from here", "until I reach…") — no concrete resolvable
  destination;
- `seeks_encounter`: travel-until-someone ("until I run into someone",
  "look for anyone on the road").
Both route to the Assessor pre-move. Concrete named destinations keep
today's resolve/mint path untouched.

## 6. Slices (each through the full pipeline)

- **G1 — FRONTIER PLACE-GROWTH:** `moves_open` → Assessor → one place stub
  + connection + committed move + furnish + arrival render. Acceptance:
  the Ironhold probe's turns 8-10 class (flee downstream) lands somewhere
  real; canon displaces.
- **G2 — ENCOUNTER-GROWTH:** `seeks_encounter` → Assessor → person/group
  stub staged on the road (Gregor + Kip); NPC machinery picks them up as
  ordinary cast (npc_turn, delivery-eligible, person_can_act).
- **G3 — REGION MEMORY & SOCIETY:** grown places accrete a region style
  card (the "supported style" bar — the new town remembers WHY it exists
  and what the player did arriving); conclude→continue authors ch2 against
  grown territory (the hide-and-integrate case).
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
  Vehicle: the displaced-conclusion probe extended (companion leg + the
  five bars in the critic addendum); the displaced probe's original
  three-bar form remains as the G1/G3 slice gate.

## 7. Open questions for review

- The Assessor's tier (cheap vs main) and its budget interaction with the
  one-mint-per-turn LWG discipline (proposal: growth counts as the turn's
  mint — one generative act per turn total).
- Whether G1's place stubs ride the existing `invent_under_canon` resolve
  thunk (preferred — one doorway) or a host-built stub batch (the D3
  re-mint pattern); the answer decides who owns naming.
- Journey time: growth distance × the diegetic clock (the #113 route-price
  machinery should price grown roads consistently).
- Latency: the Ironhold probe's 400-450s turns need decomposition before
  G1 adds a cohort to the movement path (possibly the failed-grant retry
  chains — G1 may actually REMOVE cost by replacing repeated failures with
  one assessment).
