# Living-World Generator — the regenerative arc engine (spec, for round-robin)

**Status:** DRAFT for full deliberation (K → Cx → PB). The capstone of the
world-as-generative-substrate arc: after/around the authored story, the world
keeps producing engaging situations, so endless play feels *alive* rather than
parked. Host-side over the arc layer + shipped reads; no new engine primitive
expected (PB to confirm).

## 1. The problem ("then what?")
Today there is ONE authored arc. NPCs are reactive (answer the player, never
initiate); clocks push toward the destination; once it's reached the arc is
spent. So when the case is solved and the detective comes back the next day:
nothing generates the next case. A concluded story that forgot to end. Endless
mode needs the world to **keep moving and keep throwing up situations** — and to
handle arcs that **fail or become incompletable** without dead-ending.

## 2. Shape: a PORTFOLIO of arcs, not one
Generalize the arc layer from a single `arc:main` to a **registry of `arc:*`**
(the grammar already namespaces beats/clocks/pins by `arc_id`). Like an RPG's
main quest + side quests:
- **The main arc carries the terminal** — win/loss ends the *story* (`scenario_mode
  == win_loss`).
- **Side arcs are endless-style** — they resolve diegetically, in-world, and
  regenerate; they never flip `ended`.
- Multiple arcs are active at once; `arc_outcome` is evaluated per-arc; only the
  main arc's outcome terminates.

## 3. Arc lifecycle: death is FUEL, not error
Each arc: `active → won | lost | cancelled | incompletable`. The non-won terminals
are first-class **content**, not failures of the system:
- **incompletable** — required beats went `unreachable_if` and repair is exhausted
  (the culprit died before justice; the macguffin was destroyed; the path is
  foreclosed). Distinct from the refusal-clock timeout.
- On any terminal, the world (a) **acknowledges it diegetically** (the case goes
  cold; the chance is gone — a real beat, never a silent stall), and (b) **emits
  FALLOUT** — standing tensions seeded from the unresolved stakes (the unpunished
  culprit is now a free threat; the destroyed macguffin forces a new plan; the
  antagonized NPC nurses a grievance). **Fallout is generator fuel.** So a failed
  arc *seeds the next one*.

## 4. The generator: a DM with three triggers
A paced, fail-open **DM cohort** (good-improv energy) that mints fresh mini-arcs
from the world's standing tensions. Three triggers:
- **Opportunistic** (the heart) — each turn (paced, not every turn) it reads *what
  the player just changed* + the standing tensions and asks the DM's question:
  *is there an opening for an engaging development?* It seeds a complication,
  challenge, hook, or consequence grounded in the world's premises + genre voice.
  (Player antagonized the clerk → her drive points at a confrontation; player
  exposed the books → a powerful figure moves to bury it.)
- **Regenerative** — an arc concluded/died → spawn a new arc from its fallout.
- **Ambient** — too many quiet turns → the world throws something up.

Each generated arc is a real `arc:<id>` (a beat or two + a clock + a small
conclusion-shape), minted through the **existing arc grammar** — the same
machinery, regenerated. The narrator surfaces the hook diegetically (a runner
bursts in…); the player pursues it like any arc.

## 5. The fuel (all already authored/shipped)
- **NPC dispositional spines** — seeded `drive`/`fear`/`breaks_if` (an NPC acting
  on an unaddressed drive IS a situation).
- **Dangling threads** — the situation lens / `live_threads`.
- **World premises** — the generative substrate (genre physics, social structure,
  implied offstage scope) — the sibling spec; lets generated arcs obey the world's
  logic.
- **Arc-fallout** — the unresolved stakes of a dead/won arc.
- **The player's recent changes** — the turn's committed facts (the opportunistic source).
- **who_knows / frames** — who is positioned to act on what.

## 6. Discipline (restraint is the craft)
- **Paced, never spammy** — the opportunistic trigger fires on a budget/cadence,
  not every turn; a good DM waits for the moment.
- **Grounded** — generated arcs draw on premises + established entities; they go
  through the same ingest **gate** (no fiat, no momentous fabrication outside the
  generator's authority).
- **Concealment intact** — generated arcs are authored in `plot:` (hidden), the
  narrator stays blind; their hooks reach the player as briefing directives.
- **Fail-open** — a generator miss never breaks the turn; the world just stays quiet.
- **Bounded portfolio** — a cap on concurrent active arcs (avoid quest-soup).

## 7. Phased build
- **P1 — multi-arc portfolio + lifecycle.** `arc:*` registry; per-arc outcome;
  main-arc-terminal vs side-arc-endless; the `cancelled|incompletable` states +
  diegetic acknowledgment + fallout emission. (No generation yet — but a hand-
  authored second arc works, and arc-death stops dead-ending.)
- **P2 — the opportunistic DM generator.** The cohort + the three triggers,
  minting mini-arcs from fuel. Paced, gated, fail-open.
- **P3 — procedural arc-gen depth.** Richer generated arcs (multi-beat, clue
  trails via foreshadow pins, tied to premises).

## 8. Open questions per reviewer
- **Kernos (host discipline):** Is the portfolio + DM-generator the right shape
  over the arc layer, or does it blur the arc/host boundary? Pacing/restraint
  discipline — how to keep the DM from over-producing? Does arc-death-emits-fallout
  fit the conclusion machinery cleanly?
- **Cx (adversarial):** Failure modes — generator spam / quest-soup; incoherent or
  contradictory generated arcs; arc-death → fallout → arc-death loops; the
  opportunistic trigger misreading player changes; fallout-tension explosion;
  generated arcs leaking the hidden main arc. Where are the structural guards
  (caps, the gate, the dedupe)?
- **PB (engine truth):** Does multi-arc + the generation reads (threads, premises,
  who_knows, the player's committed delta) compose on shipped porcelain? Any new
  primitive (I believe none — host orchestration over the arc grammar + existing
  reads)? Is the `arc:*` registry just more `plot:` rows (yes?)?

## 9. Not built
Spec for deliberation. On consensus: build P1 → code-review (Cx) → live-test, then
P2, etc. Nothing ships before the round-robin lands.
