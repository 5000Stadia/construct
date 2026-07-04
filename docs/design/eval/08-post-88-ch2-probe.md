# 08 — Post-#88 live probe: bodycase 18-turn run + chapter-2 continuation

**Run:** `logs/harness-1782973659.md` (2026-07-02, probes on, fresh slot, post-#88/#89 code;
also post-#82/#85/#83/#87 — those need a rebuilt world to show, this slot predates them).
**Purpose:** the live acceptance Cx 385 left to us: does the chapter-2 doorway open at a
real new time/place with an outro→hook bridge, and does the two-beat close render?

## Verdict summary

| #88 slice | Live result |
|---|---|
| S4 doorway — time | **PASS.** Ch1 ends "Day 1, night" (Wapping Stairs); ch2 opens at dawn ("Dawn lies grey against the window glass", CH2 t2). Next-phase jump committed as engine truth. |
| S4 doorway — place | **PASS.** Protagonist reopens at the briefing room — the prior episode's opening place — not restaged at the terminal scene (the pried warehouse door). |
| S4 doorway — items | **PASS.** Only the brass token she already carried appears ("wrapped from the first examination… in your pocket"); nothing minted by the intro. The eval/05 item-minting complaint does not recur. |
| Outro→hook bridge | **HOOK: strong** (the bought-tongue witness; token callback; reputation "the one from Bluegate Yard"). **OUTRO: not exercised** — see below. |
| Two-beat close (B) | **Not exercised this run.** The player-agent's final C move was physical (forcing the door → resolution-deck failure-with-opportunity), never a conclusive accusation; the arc concluded silently via its world-condition, so no reckoning scene had cause to render. A scripted probe (`scripts/probe_88.py`, log `logs/probe88-*.md`) exercises the gate + close directly — results appended below. |
| Clarification gate (A) | Same — not triggered by this run's inputs; covered by the scripted probe. |

## New findings (this run)

1. **Ch2-opening ghost hook (NEW, high-priority craft/continuity):** the continuation
   opening narrates a duty clerk and a young woman delivering the hook ("A police sergeant
   has bought my tongue") — then CH2 turn 1: *"No one is in the room now to answer aloud"*
   and turn 2: *"Your instruction falls into the stale lamplight with no man there."* The
   hook cast exists only in the opening prose; nothing committed them present, so the
   presence truth (correctly) denies them a turn later. The opening seam needs what the
   turn loop already has: hook characters staged as canon rows before (or by) the opening,
   or the opening barred from staging uncommitted persons. Same family as the founder's
   "why are nell and grieves here???" — inverted: instead of ghosts lingering, the
   invited guest is never real.
2. **Silent conclude:** the chapter "ended" for the continuation check (arc world-condition
   met) without any on-screen closure — no End-of-Chapter, no reckoning — and ch2's turn-1
   narration then invented "your earlier matter came good and is closed." The staged-commitment
   path (#88) renders closure only when the player commits; a quietly-satisfied arc leaves the
   episode boundary invisible to the player. Worth a design note: should arc_concluded-without-
   commitment surface a soft diegetic closure beat before any continuation?
3. Turn-quality throughout the 18 turns held the eval/05 standard (grounded opening, probe
   honesty — the hidden-door assert and the records-room search both denied cleanly, in-world).

## Disposition

- Doorway + intro: **accepted live** (with Cx 385's deterministic green, S4 closes).
- Two-beat close + gate: pending the scripted probe appended below.
- Finding 1 filed as the next continuity fix (ch2-opening presence commit); finding 2 routed
  to Cx as a design question with the #82-#87 review letter.

---

## Scripted probe leg 1 (`logs/probe88-1782977178.md`, fresh slot)

| Seam | Result |
|---|---|
| Clarification gate (A) | **PASS live.** The staged-in-the-wrong-room accusation (t6: "I put it to Liddell to his face" — but Liddell absent) triggered exactly one clarification, rendered in-fiction and precise: *"Your charge falls in the small lamp-lit briefing room… not onto Arthur Liddell. He is not here to answer it."* No grade, no false loss — the #88 answer to the founder's wrong-place accusation. `commitment_clarified` receipt written (once-per-episode consumed). |
| Early conclusive push (t4) | "It was Arthur Liddell. Case closed." at turn 4 (below the earned bar) drew the world's own pushback — Reed: *"a name is not a charge, and a charge is not a conviction… make the brass answer to the scales — then say it."* The staging-aware texture works before the gate is even armed. |
| **NEW: the false journey (t5)** | "I go to Arthur Liddell at his warehouse, with Reed" — the narration rendered the full trip (wet cobble, the foreman's lamp, Reed stopping at the office door) while **canon never moved**; t6's engine truth still had the player in the briefing room. The prose journey was a ghost — exactly the narrated-arrival family (#80, PB-gated narration seam; the classify likely read confront-intent, not movement). The gate then saved the experience, but the map-governs violation is real. Filed as fresh #80 evidence. |
| Two-beat close (B) | Not reached in leg 1 (the false journey kept the player from Liddell). Leg 2 (resume, explicit place move) below. |

## Scripted probe leg 2 (`logs/probe88b-1782978648.md`, resumed slot)

| Seam | Result |
|---|---|
| Companion carry (#82, live) | **PASS.** "Reed and I go…" — Reed's `in` committed with the move; he is engine-present at the destination in every following turn. |
| **NEW: the floating mint (task #91)** | "…to the Liddell warehouse, to the foreman's office" minted `place:foreman_s_office` as a **top-level** place — engine truth after the turn: Clara+Reed in the floating office, Liddell still in `place:liddell_warehouse`. Turn 1's vivid Liddell-at-his-desk scene was narrator improv against the wrong map; turns 2–3 then honestly render him gone ("No man stands behind the desk"). Fix-shape: mint contained in the embedded referent (`in=place:liddell_warehouse`) or bind the compound phrase to it outright. |
| Coverage bounce | The face-to-(absent)-face accusation drew the earned-conclusion resistance, staging-aware and in-voice: Reed's *"not hang a murder charge on brass and access before the scales answer in writing."* No false grade on thin pillars — coverage-as-effect holding live. |
| Once-per-episode gate | Confirmed: leg 1's clarification consumed the receipt; leg 2's unstaged moment flowed to the bounce instead of a second clarification. |
| Two-beat close (B) | **Still unobserved live** — a 10-turn scripted probe cannot honestly fill bodycase's pillars, and the close only renders on an earned, staged commitment (by design). Deterministic contract is Cx-green (385) and the eval answer-key (bodycase t18) shows the renderer writes the scene when the commitment lands. Final live observation falls to founder play post-reboot. |

## Final disposition (#88 live acceptance)

Doorway (time/place/items) — **PASS**. Clarification gate — **PASS** (precise, in-fiction,
once). Coverage bounce + staging texture — **PASS**. Two-beat close — deterministically
green, live rendering pending a coverage-complete ending (founder play). New work filed:
#90 (ch2-opening ghost hook), #91 (floating compound mint), fresh #80 evidence (the false
journey), and the silent-conclude design question to Cx.
