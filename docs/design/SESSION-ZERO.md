# Session Zero — the unified creation interview (design draft)

**Status:** Design draft for review (Kernos CC, then Codex pass before
build). No code. Companion to `ARC-LAYER.md` (the DESTINATION stage
authors what that doc specifies). Standing rulings inherited: frame
writes via `ingest_structured(frame=)` only; provider interface built
first, Codex default (letters 003/004/005/007).

**One sentence:** one interview is the front door for every game —
ingest-a-book and build-live are the same wizard under a
which-sections-are-known switch, and its output is a pristine, reusable
**world scenario** (charter, spine, frames, covenants, hidden arc) that
play never writes to.

## 0. Scenarios and playthroughs (letters 012/013 — founder's launch model)

- A **scenario** is session zero's output: the pristine genesis `.world`
  — self-identifying via its charter, shareable, never written by play.
- A **playthrough** is the player's accumulated canon within a scenario.
  **v1: exactly one playthrough slot per scenario** (founder scope call,
  letter 013) — a single save file the playthrough appends to. "Start
  from the beginning" recopies the pristine scenario over the slot (one
  file copy; the old save is replaced, the scenario untouched). Two
  files per scenario, one copy operation — no fork machinery, no
  save-naming UX in v1.
- The *boundary* is the load-bearing part: it keeps "start over"
  non-destructive to the scenario and keeps scenarios shareable.
  Deferred-not-designed-out: multiple named saves post-v1, auto-labeled
  by last location ("Eastmere — the Drowned Lantern") via charter +
  `locate(player)` — a small additive change because the boundary
  exists, never a refactor.

**Launch flow:** greet → choose a scenario from the library (each
self-IDs via charter) or create new via this wizard → resume the
playthrough slot OR start from the beginning → world starts.

---

## 1. The state machine

```
GREET ──launch (scenario chosen)──→ resume slot | fresh copy → re-enter
  │ create new scenario
  ▼
PROVIDER → PATH ──A: ingest──→ WORLD-A (registry-first ingestion)
                ──B: live ───→ WORLD-B (charter + constitutive-spine interview)
  → SAFETY (lines and veils)
  → ENTRY (WHERE, then WHO)
  → DESTINATION (theme consent → arc authoring)
  → LINT (arc lint + output-contract check; bounded regeneration)
  → START (save; establishing materialization; opening render)
```

Stages are **checkpointed and resumable**: each completion is logged to
`session:main`; re-entering session zero skips completed stages. All
writes are appends — an interrupted interview loses nothing.

## 2. The which-sections-are-known switch

One wizard; the paths differ only in which sections arrive pre-filled:

| Section | Path A — ingest a work | Path B — live fiction |
|---|---|---|
| Charter (`world:self`) | Derived (title, `genre_era`, `derived_from`) — player confirms | Interviewed: genre, era, tone → charter rows |
| World content | Registry-first ingestion authors everything | Constitutive-spine interview: the place, 2–4 key NPCs, the opening situation; `world_defining` pins |
| Characters | From the registry (character sheets) | Authored in the interview |
| Entry WHERE | Event-spine anchors offered | Defaults to "now" (young timeline) |
| Entry WHO | Canon character or new-under-canon | Usually the authored protagonist; same options |
| DESTINATION | Theme consent over mined tensions; beats thread existing canon | Theme consent; arc instantiated over the authored spine |

## 3. The stages

### GREET
List the scenario library — each self-identifying via its charter (the
ship in a bottle, labeled on the glass): title, description, stance.
Scenario chosen → **resume** (open its playthrough slot at the head) or
**start from the beginning** (recopy pristine scenario over the slot),
then `World.open(slot, model=shim)`, materialize, re-enter — the wizard
is skipped entirely. Create-new → PROVIDER (this wizard, producing a new
pristine scenario).

### PROVIDER (letter 003: alongside, but distinct from, world creation)
Detect `~/.codex/auth.json` → Codex is the working zero-credit default,
one confirmation line. Otherwise (or on request): enter any provider
(OpenAI / Anthropic / local endpoint / …) as an implementation of the
provider interface. The selection is honored EVERYWHERE a model is
called — engine `model=` and every cohort. **Provider config and
credentials live host-side only** (player profile), NEVER in the
`.world` file: worlds are shippable and must carry no secrets. 401 →
fail fast and loud with the fix ("run `codex login`"), never retry
silently.

### WORLD-A (ingest)
Registry-first ingestion of the work (the engine's pipeline; the host
supplies text and the scene-cursor discipline). Charter rows derived and
confirmed with the player. The event spine, character registry, and
evidence-graph sketch become ENTRY/DESTINATION inputs.

### WORLD-B (live)
Short interview, in order: genre/era/tone (→ charter + render
constraints); the place (constitutive: rooms, fixtures, the lateral
graph at coarse precision — the lidar discipline applies: anchor at
interviewed precision, never finer); 2–4 key NPCs **each given the
minimum dispositional spine** (§5); the opening situation (establishing
STATE + `world_defining` pins). Output committed via `ingest_structured`
as `stated` — session zero is authoring time; the player and interviewer
are the author.

### SAFETY — lines and veils
Tabletop safety tools as architecture (Kernos covenant pattern): lines
(never appears) and veils (happens off-screen) collected after PATH
(genre informs the defaults offered). Stored in the **host-side player
profile**, evaluated in the render path every turn — the player's
constitution outranks the renderer's mood. Not world content: shipping a
world to a friend must not ship your boundaries. (Obvious call, recorded:
profile-side, not `session:main`.)

### ENTRY — WHERE, then WHO
**WHERE:** an `as_of` coordinate, not a fixed scene. Path A offers
anchors mined from the event spine ("before the meter went dark");
fuzzy player phrasing resolves by event-spine anchor search with
interval slop (whitepaper §19.3.4). Path B defaults to now.
**WHO:** (a) a canon character — the player's frame binds to that
entity's existing `knows:<id>` frame *as of the entry point*; they
inherit exactly that information state, structurally (play the detective
or play the clerk who hid the core — same world, opposite games);
(b) a new character — collaboratively authored (committed `stated`), or
engine-invented on request via `resolve()` (the sanctioned invention
path, landing `generated`-in-canon by resolver authority); either way
the spine invariant (§5) is enforced before DESTINATION runs.
Player-reserved slots use the LIVE `deny`/`reserve` thunk policy
(letter 007).

### DESTINATION — theme consent → arc authoring
Per ARC-LAYER §6: mine the chosen character's DISPOSITIONAL rows for the
strongest tension pair; propose 2–3 **themes** (delta types with flavor
— "a story about the cost of mercy"), or take the player's stated
desired end and reduce it to a shape. The player consents to the theme;
the instantiation (beats, clocks, refusal variant, premise) is generated
by the arc author (main tier, canon-constrained) and committed to
`plot:main` — invisible to the player from the first turn. Event items
follow the agent/patient authoring convention (letter 007).

### LINT → START
Arc lint (ARC-LAYER §9) + the output-contract check (§4 below). Failures
→ bounded regeneration (≤3 attempts per failing component), then loud
fail with the named deficit — never a silently degraded arc. On green:
**save the pristine scenario, copy it into its playthrough slot** (§0),
`materialize(establishing_set, as_of=entry)` on the slot, opening
render. The world starts — play appends to the slot only; the scenario
is never touched again.

## 4. The output contract (both paths, identical shape)

| Output | Where | Provenance |
|---|---|---|
| Charter: `world:self` — stance=fiction, title, description, genre_era, derived_from (A only) | canon | `stated` |
| Constitutive spine + `world_defining` pins | canon | `stated` (A: ingested) |
| NPC knowledge seeding | `knows:<id>` per NPC | `stated` (authoring time) |
| Player frame binding (canon char) or new-character rows | canon + `knows:` | `stated` / `generated`-via-resolve |
| The arc: shape, beats, clocks, refusal clock, premise | `plot:main` | `stated` |
| Turn-zero row; stage checkpoints | `session:main` | host ledger |
| Lines and veils; provider config + credentials | host-side player profile | — (never in the world file) |

Row-4 provenance, spelled out (letter 008, note 1): a
*collaboratively-authored* new character commits `stated` — the player
and interviewer are the author; an *engine-invented-on-request* character
routes through `resolve()` and lands `generated` by resolver authority.
The split is by who invented, never by path.

**The session-zero invariant** (ARC-LAYER §6): no playable character
without a minimum dispositional spine — **two ranked drives + one fear
or `breaks_if`**. Thin characters get their spine deepened in the
interview before arc generation; this is what makes the conclusion
generator *computable* for an arbitrary character.

## 5. Model usage

One interviewer agent (main tier) drives the conversation; per-stage
strict-contract extraction calls (cheap tier) turn answers into
structured items for the gate. Arc authoring is one main-tier call.
Lint and the output-contract check are deterministic — no model. Every
call routes through the provider interface; tier hints per letter 004
(engine gets a main-tier-bound callable).

## 6. Failure modes

- Ingestion failure (Path A): loud, with the engine's receipt; never a
  partially-ingested world presented as whole.
- Lint failure: bounded regeneration, then loud fail naming the deficit.
- Provider 401/timeout: fail fast (~10-min bound house standard), name
  the fix, never degrade silently.
- Interview abandoned: checkpoints in `session:main` make resumption
  free; nothing to clean up (appends only).

## 7. Eval criteria (session zero's own)

- (a) Both paths emit the identical output contract (§4) — diffable.
- (b) Charter complete per letter 026; saved world self-identifies in
  GREET.
- (c) Every playable character passes the spine invariant.
- (d) The generated arc passes lint on the first or a bounded retry.
- (e) `.world` file contains zero credentials / profile data (grep-able).
- (f) Re-entry: save immediately after START, reload cold,
  `materialize(establishing_set)` — coherent re-entry (the §19.2
  criterion exercised at birth).
- (g) Canon-character entry: the player's first-turn briefing contains
  only `knows:<id>`-frame content (structural non-leak, diffable).
  **Headline artifact, not a checklist line** (letter 008, note 2): when
  the eval harness is built, (g) ships as the demo — the detective's
  first turn vs. the clerk's first turn over the same world, diffed,
  provably different information states. The structural-non-leak proof
  that sells the whole thesis.

## 8. Open questions (tracked)

1. GREET-stage world browsing at scale (dozens of saved worlds) —
   trivial now; revisit with a library UX later.
2. Mid-campaign re-entry to DESTINATION (player wants a new arc after
   concluding one) — the machinery supports a fresh `plot:arc2` frame;
   the interview flow for it is deferred to post-first-playable.
3. Multiplayer session zero (multiple player frames) — out of scope for
   first playable; the frame machinery does not preclude it.
