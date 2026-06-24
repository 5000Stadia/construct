# Story Shape & Resolution — *the player concludes; the world never tells; the epilogue delights*

**Status:** design-first (house method). **Mesh deliberation COMPLETE** (round-robin
HD→Kernos→Cx; no PB primitive). **Kernos 076: endorsed** (1 load-bearing correction
[Q2 §4↔§5 → structural absence] + 2 refinements [Q1 un-conflation, Q3 judgment-type] +
1 named dependency [Q4 neutral-narrator] — all folded in below). **Cx 023: YELLOW** —
architecture sound, GREEN-able with **two blocking fixes** before implement:
1. **Hold-mode must be ANSWER-FREE.** The shipped `_concealment_directive`
   (`turnloop.py` `HIDDEN — THE MYSTERY'S ANSWER` block) IS the §4 anti-pattern — it
   hands the narrator the answer + "don't reveal," survivable today only because the
   Cx-022 gate backstops it. The build must **replace it with structural absence**:
   the held truth is read only by deterministic arc/reveal code, never in the hold-mode
   briefing. (Gate demotion is GREEN *iff* this holds.)
2. **Neutral-narrator / no-verdict-weighting** must be a first-class hold-mode directive
   + regression test (not buried) — a leading theory ("so it was Cray, right?") gets
   only flat observable facts / diegetic deflection, never a confirm/deny/wink/tonal tilt.
**Cx required tests before GREEN:** (a) hold-mode prompt contains no canon answer /
protected value / `plot:` row / HIDDEN block; (b) leading theory → neutral/deflect;
(c) wrong commitment terminates + stores a wrong/partial grade, epilogue reveals truth
with no mid-play correction; (d) survival + romance profiles exercise non-claim
judgment types with no special-case engine code; (e) trace proves no new always-on
per-turn model call. **Latency:** confirmed; note the player-input extraction also feeds
ordinary mirroring / `arc_touch` / `pre_keys` — retire those consumers consciously, not
smuggle a new per-turn "did they learn it" call.
**CONCEALMENT APPROACH UPDATED (2026-06-22, founder + Cx 024/025):** §4–§6's
*structural-absence* model is **superseded by the card model** in `STORY-SHAPES.md` —
the narrator-DM *knows* the destination (you can't foreshadow a reveal you don't know),
guarded by "don't blurt the unearned payoff" + brute-force deflection, not by hiding the
answer from the narrator. The real leak was the *seed* (now fixed), not a blurting DM.
Read `STORY-SHAPES.md` for the genre layer (9 blendable shapes + the thread schema) this
win-model sits on; the win-model's `commitment` is now a per-shape *capture form*
(claim / state / action / choice…), not always a `claim:` fact.

**Subsumes & extends:** `CONVERGENCE-TO-CONCLUSION.md` (Phase 1 shipped),
`EXTRACTION-AND-DISCOVERY.md` (the latency coupling), and the Cx-022 concealment
notes. This is the single coherent picture they were each a facet of.

**Founder's thesis (2026-06, distilled from the live-iteration thread):** Every story
is an *interesting plot line that converges to a conclusory scene where what will be,
will be.* The world is honest and neutral — it never spoon-feeds, never shoehorns the
player to the "right" destination. The player draws their own conclusions from the
evidence, **and may be wrong** (the wrong person may go to jail). The DM knows the
truth, sprinkles hooks, holds the reveal, and at the curtain has *fun* showing its
hand — the twist, and all the interesting bits the player never uncovered. And the
*shape* of all this is **genre-specific**: zombie survival looks nothing like Harry
Potter; each setting defines what a good story and a good ending even *are*.

---

## 1. The principle

We were over-fitting to one genre (whodunit) and, worse, treating concealment as
*security* — keys, gates, quarantine, licensing. That's vault-thinking for what is
really **DM craft**. The durable model isn't a stronger vault; it's a well-briefed DM
running a genre the player chose, who:

- knows more than they tell,
- lays an honest trail (real clues *and* red herrings),
- never tips the scales or hands over the answer,
- lets the player commit to a conclusion — right or wrong,
- and at the end, *enjoys* revealing what was really going on.

This is **more alive, not less** — the world is allowed to mislead you, and you're
allowed to be wrong, which is the whole pleasure.

## 2. The universal spine (genre-agnostic)

Every playthrough, regardless of genre:

1. **An interesting plot line** with a destination — a **conclusory scene** the story
   bends toward (the arc already models this: `ConclusionShape`, `current_phase`,
   `climax_ready`, `navigate`).
2. **Convergence, not coercion.** All roads *lead to the conclusory scene* — the
   *decision point* — never to a *predetermined answer*. Nudges and the relocate-the-
   beat machinery bring the *moment* to wherever the player is; they never bias *which*
   conclusion the player reaches. (Sharpens `CONVERGENCE-TO-CONCLUSION.md`: converge the
   **scene**, not the verdict.)
3. **The world is honest and neutral.** It surfaces what's observable — including
   misleading-but-true detail — and never annotates "this is the real clue." No
   spoon-feeding, no shoehorning.
4. **The DM knows more than it tells**, paced by the arc (hold vs. reveal).
5. **The conclusion is the player's** — they act/commit at the conclusory scene; the
   outcome *flows from what they did*. "What will be, will be."
6. **The epilogue pays off** — the truth at last, the twist, and a delighted reveal of
   the interesting bits that went unseen.

## 3. The genre fill — *what makes a good story* here* (the game-type layer)*

The spine is constant; the **fill** is genre-specific and already has a home: the
game-type taxonomy (`play_styles_data.py`, `GAME-TYPE-TAXONOMY.md`) and the per-turn
`play_style` briefing directive. The engine has **no single notion of "a good story"**
— it executes the *genre's* notion, supplied by this layer. Each story profile
declares:

- **Conclusory scene** — what the player does at the climax (accuse / outlast / confront
  / confess / pull it off).
- **Concealment** — what (if anything) is held back from the player until earned/curtain.
  **Genre-conditional**, not a universal subsystem.
- **Earn / outcome** — what "winning" and "losing" mean, and the space between (e.g.
  *right*, *wrong-but-confident*, *pyrrhic*).
- **Tone & pacing** — what to dramatize vs. hand-wave; what a satisfying beat *is*.
- **Epilogue flavor** — how the payoff lands.

### Three profiles (the founder's test — these must all fit the same spine)

| | **Mystery (noir whodunit)** | **Zombie survival** | **Hero's journey (Harry Potter)** |
|---|---|---|---|
| Conclusory scene | name the culprit + cite evidence (an **accusation**) | the last stand / the gate reached at dawn | the confrontation + a **choice** |
| Concealment | strong — *who did it* is hidden; clues + red herrings | light/none — threat is overt; maybe "who's bitten," "where's safe" | medium — the villain's plan / a betrayal / a prophecy |
| Earn / outcome | right → vindicated; **wrong → wrong person jailed** | survive / escape / fall — degrees of cost | prevail / falter; the choice defines the ending |
| Don't-shoehorn | never confirm a theory; let them mis-conclude | never guarantee safety; scarcity is real | never hand the "right" choice; let them choose |
| Epilogue | the twist + *"here's what was really going on"* | who/what was lost, what the survivors learn | the cost of the choice, the world after |

Same spine — *interesting plot → conclusory scene → outcome from play → epilogue
payoff* — three completely different fills. That's the bar: the architecture is correct
only if the *same code* runs all three by swapping the game-type profile.

## 4. The elegant mechanism — **arc = WHEN, narrator-DM = HOW**

Split authority cleanly so there's no per-turn "did they earn it?" inference:

- **The arc owns the dial** (deterministic, free — reads state we already compute):
  *hold-mode* vs *reveal/conclusory-mode*. It's the adventure module: it knows when the
  conclusory scene unlocks (setup beats landed, climax phase reached, the player has
  acted on the right thing).
- **The narrator is the DM**, primed each turn for the current mode. **The hold-mode
  briefing carries ZERO answer-bearing content (Kernos 076, Q2 — load-bearing).** The
  narrator never *sees* the held truth — structural absence, not a directive-to-hold (a
  secret in the context window guarded only by "don't say it" is *more* leakable, the
  turn-loop round-robin already ruled). "Priming" = priming **what to surface**, never
  the answer:
  - *Hold-mode:* "You are laying a trail toward a held truth you do **not** see.
    Surface these hooks [the clue/foreshadow bank]; present clues and red herrings
    **flatly**; deflect direct probes and drop a thread. **Do NOT weight the evidence**
    — never drift toward confirming or denying the player's theory (Kernos 076, Q4: the
    neutral-narrator discipline, the flip side of concealment). Let them interpret."
  - *Reveal/conclusory-mode:* "It's time. Land the conclusory scene the way this genre
    wants it landed." (This is the one place the held truth is surfaced — via the
    explicit reveal path, never the hold-mode briefing.)
- **The conclusion is the player's claim, captured once.** At the conclusory scene the
  player *commits* (accuses / makes the stand / chooses). The engine evaluates that
  commitment against canon **once** — not every turn — yielding the outcome
  (right / wrong / between).
- **Reveals record themselves — no extraction.** When the DM does reveal something, the
  render call (which we make anyway) returns its prose **plus a small `revealed`
  signal**. The host writes that fact through the doorway. No second extraction pass to
  *infer* what was revealed.

## 5. Concealment is priming, not a vault (and it's genre-conditional)

Replace the keys/gate/quarantine apparatus with:

- **Structural absence is the PRIMARY defense (Kernos 076, Q2).** The held truth lives
  in canon/`plot:`, read only by the deterministic **arc dial** and the **reveal path**
  — **never** in the player frame and **never in the hold-mode narrator briefing.** The
  narrator is briefed strictly from the player frame + the trail-laying directive, so it
  cannot leak what it never sees. (The original leak was an *un-primed* narrator
  *answering from canon it had been handed*; the fix is to stop handing it, not to add a
  louder "don't tell.")
- **A held truth never auto-enters the player frame from prose.** It enters only via the
  explicit `revealed`/conclusory path, gated by the arc's mode. No `pre_keys`, no
  per-turn licensing.
- **Genre-conditional:** a survival story may hold nothing; a mystery holds the culprit.
  The profile says what (if anything) to hold.

The Cx-022 strict gate was always the *secondary* check (on extraction); structural
absence was the real defense. So demoting the gate is safe **precisely because the
narrator still never sees the secret** — it can stay as a cheap backstop for concealing
genres, and it no longer needs the player-input extraction to feed it.

## 6. The epilogue — the dessert course

The curtain is the one place concealment lifts and the DM gets to be a showman. It is
**not** a dry "here's the answer":

1. **Mine the irony delta** — the engine already tracks the gap between what's *true*
   (canon) and what the *player learned* (player frame): `frame_diff(canon,
   player_frame)`. That delta *is* "everything interesting that was never revealed."
2. **Rank by interestingness** — the twist, the secret walked past, the NPC who was
   more than they seemed, *what the red herring actually was*, the missed correlation —
   over mundane leftovers.
3. **Reconcile the player's conclusion with the truth.** If they were wrong, *savor the
   twist* — Sherlock over his notes: *"the print I trusted was smudged before the
   murder; the real proof was the missing ledger page — so it was ___."*
4. **Have fun with it**, in the genre's flavor. Spill the good stuff they missed.

(Extends the existing terminal-epilogue, which already lifts concealment and names the
cast — this makes it mine the *delta* and play the *twist*.)

## 7. What this changes in the arc layer

The one real structural change: the **win-model**. Today the destination is often
`InFrame(knows:player, <answer>)` — *the engine deciding the player "knows."* That is
exactly the shoehorning we're rejecting. Replace with:

- **Conclusory commitment → judged against canon.** The destination is the player making
  their genre-appropriate commitment; the outcome is computed from commitment vs. canon
  (+ the genre's outcome space). The held answer never needs to land in the player frame
  mid-play.
- **A richer outcome space** per profile (right / wrong-but-confident / pyrrhic / …),
  feeding the epilogue's twist.
- Beats shift from "player_learns X" (engine hands it over) to "player has the means to
  conclude" + "player commits." Clues/evidence still enter the player frame freely —
  they're observable, not the held answer.

## 8. Latency payoff (why this is also the fast answer)

Because **nothing hands over the answer mid-play**, there is no per-turn "did they earn
it?" to detect — so the **per-turn player-input extraction (~11s) falls away** with no
loss of protection (see `EXTRACTION-AND-DISCOVERY.md` for the coupling it breaks). We
evaluate the player's commitment **once**, at the conclusory scene. The *render*
extraction stays (authoritative canon capture + contradiction guard, genre-agnostic).
PB's prompt-trim (letter 082) cuts the remaining render-extraction cost.

## 9. What this reuses (grounded, not greenfield)

- Arc: `ConclusionShape`, `current_phase`, `climax_ready`, `navigate`, beats as
  path-independent conditions.
- Game-type taxonomy + `play_style` briefing directive = the genre-fill home.
- Pins/foreshadow escalation = the clue/hook bank ("sprinkle the trail").
- Terminal epilogue (concealment lifts at the curtain) + `frame_diff` irony delta = the
  dessert course.
- Convergence Phase 1 (act-aware + relocate directive) = the "lead to the conclusory
  scene" spine — re-aimed at the *scene*, not the verdict.

## 10. Build sequence (design-first; each its own pass + review)

1. **Story profiles on the game-type layer** — declare per profile: conclusory scene,
   concealment posture, outcome space, epilogue flavor. Author the three test profiles
   (mystery / survival / hero's-journey).
2. **Arc mode dial + ANSWER-FREE hold-mode (Cx blocking #1 & #2)** — `hold` vs
   `conclusory` from arc state (deterministic); **replace `_concealment_directive` with
   structural absence** (held truth never in the hold-mode briefing); add the
   first-class **neutral-narrator / no-verdict-weighting** directive; the `revealed`
   render-signal path; ship Cx required tests (a) + (b).
3. **Win-model swap** — conclusory-commitment-judged-against-canon, with the per-profile
   outcome space; retire `InFrame(knows:player, answer)` as the destination.
4. **Epilogue upgrade** — mine + rank the irony delta; play the twist; genre flavor.
5. **Drop the player-input extraction** (now safe) — the latency win.
6. **Verify against all three profiles** (the zombie-vs-Hogwarts test), live, logged.

## 11. Open questions (to settle before/within each pass)

- How coarse are "story profiles"? Per game-type, or a handful of archetypes the 155
  game-types map onto? (Lean: a small set of archetypes, game-types tag into one.)
- How does the player *commit* legibly across genres (accuse / declare / act) without a
  rigid command? (Lean: natural action at the conclusory scene, classified as the
  commitment — one judged call.)
- Wrong-but-confident endings: how much does the world *show* the player they erred
  before the epilogue? (Lean: little to none mid-play — the epilogue is the reveal.)
- Survival/no-concealment genres: confirm the spine degrades cleanly when "held truth"
  is empty (it should — hold-mode just has nothing to hold).

---

## Appendix A — Grounded win-model mapping (answers open-Q1, against the real grammar)

Checked against `arc/grammar.py` + `arc/executor.arc_outcome`. **The change is much
smaller than "rewrite the win-model" implies — `ConclusionShape`, `Arc`, `arc_outcome`,
the win-loss terminal, `failure_when`, and beats keep their shape.** What changes is
only *what `world_condition` is authored over.*

Today: `arc_outcome` = `"won"` if `evaluate(shape.world_condition)` is TRUE; `"lost"`
if the refusal clock fired or `failure_when` is TRUE; else `None`. And `world_condition`
is typically `InFrame(knows:player, fact:secret, culprit, rival)` — i.e. *the engine
deciding the player "knows"* (the shoehorn we're removing).

**Kernos 076 (Q1) un-conflated this:** today `world_condition` does *double duty* —
it tests both **convergence** (did the arc reach its destination) AND **correctness**
(did the player get the right answer). The fix *splits* them; it doesn't fracture them.

The mapping:
1. **`world_condition` tests CONVERGENCE only — "the player committed at the conclusory
   scene."** The terminal fires when the player commits (accuses / makes the stand /
   chooses), **regardless of right or wrong.** A wrong-but-confident accusation still
   *ends* a `win_loss` story — it just concludes with the twist that they were wrong.
   (In `endless`, the commitment is an in-world event, its outcome reflected, play
   continues — per the win/loss-binary ruling.)
2. **Correctness is a SEPARATE host judgment → graded outcome → EPILOGUE flavor, never a
   terminal condition.** At the conclusory scene the host writes the commitment fact
   (`claim:<protagonist>.accused=<entity>` / `.choice=<option>`) and, for a genre with a
   *correct* answer, a **single** commit-time judgment of its grade (vindicated /
   wrong-but-confident / pyrrhic). `arc_outcome` goes **binary → graded** — additive,
   host-side. The grade drives the epilogue; it does **not** gate whether the story ends.
3. **The judgment TYPE is genre-declared (Kernos 076, Q3)** — *not just outcome labels*,
   or "judged against canon" silently assumes the mystery's epistemic shape: claim-vs-fact
   (mystery) / action-vs-resistance (survival) / choice-vs-consequence (hero's-journey,
   no right answer). The profile declares the type; the same code runs all three.
4. **Before the player commits**, `world_condition` is FALSE → outcome `None` → the story
   continues. Exactly the current continuous-evaluation behavior.
5. **`knows:player` stays — as the EVIDENCE store**, not the win-gate. It still feeds the
   player's reasoning and the irony delta; the held answer simply never enters it in play.

**Net grammar delta:** (a) author `world_condition` over a "committed at the conclusory
scene" `claim:` fact (convergence) instead of `InFrame(knows:player, answer)`;
(b) `arc_outcome` binary → graded (host-side, profile-declared judgment type) feeding the
epilogue; (c) one host step at the conclusory scene that writes the commitment + its
grade. All host orchestration — **no engine primitive** (Kernos confirmed; consistent with
Living-World P1). The one timing risk: `world_condition` reading a `claim:` fact the host
writes mid-play (`proposed`→`canon`) — flagged for Cx/PB.

## Appendix B — The three profiles, concretely (what the game-type layer would carry)

Each profile declares its **judgment_type** (Kernos Q3), and the terminal fires on the
COMMITMENT (convergence); the grade is epilogue flavor (Kernos Q1):

```
mystery (noir whodunit)
  conclusory_scene : accusation — player names a suspect and cites evidence
  concealment      : STRONG — hold fact:culprit (+ evidence chain); clues + red herrings
  world_condition  : committed(claim:player)            # convergence — terminal on commit
  judgment_type    : claim-vs-fact (claim.accused == canon culprit?)
  graded_outcome   : vindicated / wrong-but-confident / unsolved (refusal timeout)  -> epilogue
  epilogue         : the twist + the missed bits (irony delta), savored

zombie survival
  conclusory_scene : the last stand / reach the haven by the deadline
  concealment      : NONE/LIGHT (maybe "who's bitten", "where's safe")
  world_condition  : committed(the stand/escape) OR plain-state reached(haven)/survived(N)
  judgment_type    : action-vs-resistance (the world's actual lethality)
  graded_outcome   : escaped / survived-at-cost / fell  -> epilogue
  epilogue         : who and what was lost; what the survivors carry

hero's journey (Harry Potter)
  conclusory_scene : confront the antagonist + a defining choice
  concealment      : MEDIUM — the villain's plan / a betrayal / a prophecy
  world_condition  : committed(claim:player.choice)     # convergence — terminal on choice
  judgment_type    : choice-vs-consequence (NO right answer — the choice defines the end)
  graded_outcome   : prevail / falter / pyrrhic  -> epilogue
  epilogue         : the cost of the choice; the world after
```

Same `Arc`/`ConclusionShape`/`arc_outcome` machinery; three different fills. The terminal
is `committed(...)` in every case (convergence); only the **judgment_type** and
**graded_outcome** differ — and those live host-side on the game-type layer
(`play_styles_data.py`), so the same code runs all three.
