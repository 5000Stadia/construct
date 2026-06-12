# The Turn Loop — cohort architecture (design draft)

**Status:** Design draft, folding founder direction from Kernos letter
012 (cohort roster, turn order, model tiers). This is the first thing
built at integration; the assembly DAG below is settled BEFORE the
freeze lands. Companion to ARC-LAYER.md (whose §3 navigation loop is
the arc-layer slice of this turn) and SESSION-ZERO.md (whose output
this loop plays).

**One sentence:** a turn is a serial mutation spine (writes, strict
order) followed by a parallel read fan-out joined into one narrator
briefing, rendered by the only good-tier principal — because you cannot
parallelize a read against a write it depends on, and the expensive
model runs only where genuine understanding is needed: narration and
character.

---

## 1. The principal and the cohorts

**Principal: the Narrator/GM** — speaks to the player, writes NOTHING to
canon (the render leash). Everything else is a Quiet Cohort around it:
selectively invoked, fail-open, silent. The player experiences one
world, not a committee.

## 2. The turn DAG

### Serial spine (writes; strict order — each step reads the previous step's world)

| # | Step | Tier | Detail |
|---|---|---|---|
| 1 | **Classify** | cheap | action / question / OOC / declaration. Gates the branch: question → `ask()` (no canon write); OOC → meta/save handling; action or declaration → continue. |
| 2 | **Ingest player effect** | cheap | extract world-affecting facts under the gate disciplines (irrealis filter, intention ≠ fact, cursor humility — the micro-eval path); commit to canon. Declaration in co-author mode lands `stated`-with-speaker-source (letter 027). |
| 3a | **Clock pass** | deterministic | fire due clocks (host executor), commit effects through the gate, `caused_by`-chained. Clocks read the *previous* turn's beat state (beats evaluate at 3c) — one turn of latency between a beat achievement and a clock's reaction to it, by construction. |
| 3b | **NPC world-actions** | good | present, motivated NPCs that physically act. **Decision calls parallel across NPCs; commits serialized** through the gate. |
| 3c | **Beat-evaluator** | cheap propose + deterministic verdict | runs LAST in the tick — sees all of this turn's mutations; writes beat status to `plot:` (re-eval-all-pending default, letter 006). |

### Parallel assembly fan-out (reads only; canon is now final — run concurrently)

| Read | Tier |
|---|---|
| `materialize(scene, frame=knows:player)` | deterministic (0 tokens) |
| Resonances JOIN (letter 013) | deterministic |
| Irony delta (ARC-LAYER §4.2; frame-diff read when it ships) | deterministic |
| Navigator → pacing rung (the ARC-LAYER §5 policy table) | deterministic; **only if a nudge fires**, one cheap nudge-content pick |
| NPC dialogue intents, present speakers | good, frame-scoped, parallel across NPCs |

The assembler joins these into **one narrator briefing**: the
`knows:player` scene + NPC intents + ONE pacing directive + resonances.

**The briefing contains NO `plot:` content — structural
spoiler-prevention (letter 012).** This upgrades the ARC-LAYER
concealment posture at the narrator: the narrator is leashed AND blind
to the arc. Navigation toward the destination is done by the SYSTEM
(clocks, nudges, the navigator's rung choice), never by narrator
intent. The single surface where plot-awareness crosses toward the
player is the nudge-content pick — one cheap call that reads the irony
delta's enumeration and distills ONE directive — and its output is
auditable in `session:main` like every pacing decision.

### Render and post

| # | Step | Tier | Detail |
|---|---|---|---|
| 5 | **Narrator** renders prose from the briefing | good | writes nothing. |
| 6 | **Post:** ingest the rendered output as canon (what the player saw IS canon, including its `knows:player` discovery-gating) + concealment audit | cheap + deterministic | the audit is post-hoc over the log (letter 006 note 2): any fact that entered via render unlicensed by `knows:player` ∪ briefing is flagged. |

## 3. Model tiers (founder's assignment — the default)

| Tier | Provider mapping | Used by |
|---|---|---|
| **Deterministic** | no model call | materialize, resonances, locate/fold, clock firing, beat structural verdict, irony delta, concealment audit, pacing policy table |
| **Cheap** | provider tier `"cheap"` | input-classifier, ingestion extraction, beat-candidate proposal, `refer()` tier-2, nudge-content selection |
| **Good** | provider tier `"main"` | the **Narrator** (principal) and the **NPC engines** — and ONLY these |

The punchline: a turn is two good-tier call groups (narrator + present
NPCs in parallel) over a deterministic + cheap substrate. The tier is a
parameter on every cohort interface (the provider interface already
exposes it); the table above is the default assignment, not a hard
wire.

## 4. Budget discipline

Briefing composition owns the size budget (letter 011: budget pressure
routes to composition, never to the transport; the 40KB provider cap is
the backstop, not the steering). The materialize budget parameter and
the assembler's join are where richness is shaped.

## 5. Failure policy per step

Spine steps are loud-fail (a turn that cannot ingest the player's
action surfaces the seam — DP-4). Fan-out cohorts are fail-open: a
broken resonance JOIN or a dead NPC-intent call drops that input from
the briefing and logs to `session:main`; the turn proceeds. The
narrator failing is the turn failing — loud, with the diagnostic
preserved. The concealment audit failing OPEN is itself logged loudly
(an unaudited turn is a flagged turn, never a silent one).

## 6. Eval criteria (turn-loop slice)

- (a) Serial-spine ordering observable in receipts: no assembly read
  timestamped before the tick's last commit.
- (b) Briefing payloads contain zero `plot:`-frame rows (grep-able per
  turn — the structural-concealment proof, companion to SESSION-ZERO
  criterion (g)).
- (c) NPC world-action commits serialized (no interleaved partial
  writes) while their decision calls overlap.
- (d) A turn with all cohorts failed still renders something honest
  (fail-open composition; loud seams; no hallucinated grounding).
- (e) Two good-tier call groups per turn, no more (tier-assignment
  audit over provider receipts).
