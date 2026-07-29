# ⏭️ NEXT UP — read this first

**As of 2026-07-29, this run buttoned Construct Projector up to a mature, green
state.** This file is the single loud pointer to what comes next and what is
already done, so the next session (or the next person) does not have to
reconstruct it.

---

## 🚧 THE NEXT HEADLINE: RESOLUTION-FAN §5b — chapter-boundary reshape

**Status: DESIGNED + AUDITED, NOT IMPLEMENTED.** This is the one large net-new
build left, and it is the project's core intellectual contribution (the
arc/destination layer).

**What it is.** At a chapter boundary, before the next chapter is authored,
reassess whether a *more appropriate story shape* fits where the player actually
took the story — then confirm / blend / reshape the game-type accordingly. A
player running a mystery but steadily flirting earns a mystery **+ romance** going
forward; the default is to do little or nothing (hysteresis), and it is driven by
tone and engagement, **not** by how well the player executed the genre.

**The design and the audit already exist — read them before touching code:**
- [RESOLUTION-FAN.md](RESOLUTION-FAN.md) — the DIRECTION spec (fan of endings,
  gated roll, §5a off-script handling, §5b structure-validation pass).
- [STRUCTURE-VALIDATION-AUDIT.md](STRUCTURE-VALIDATION-AUDIT.md) — why chapter 2
  doesn't reshape today, the exact seams, and the gap breakdown **G1–G4**.

**The audit already narrowed the build** (good news): genre/game-type is *already
composable* (`meta["game_type"]` is a blended list), so the fix is **G1** (a
whole-story play-reflection cohort) + **G2/G3** (write the reassessment back to
`meta["game_type"]` and feed the shape directive into the continuation
`generate_arc`) on top of existing blend machinery. **G4** (a tonal light/dark
register dial) is the only genuinely-new capability and is **deferrable**.

### ⚠️ BROAD DESIGN BEFORE IMPLEMENTATION
Do **not** start piecing out the implementation until a broad design pass settles
the open forks — the shape needs to be whole before it is coded:
1. **§5a tolerance-window** — how far off-premise before a fan is *invalidated*
   (terminate + genre reshape) vs *absorbed* as a tangent; and the founder's
   "almost randomize the player's sabotage with a new story structure" appetite —
   how much randomness, bounded how.
2. **§5b register dial (G4)** — defer (approximate a lighter register by blending a
   lighter game-type key) vs build a first-class light/dark modifier. Recommend
   defer; confirm.
3. **Composite game-type interplay** — the audit found blending already works;
   confirm no additional contract is needed when two shapes co-drive a chapter.

Then: implementation spec → **cr** review → build G1 → G2/G3 → the `genreshift`
probe (`scripts/critic_harness.py --mode genreshift`) as the green/red acceptance.

---

## ✅ What this run buttoned up (context, not action)

- **Provider default (A1)** — metered API key is the shipped default; the codex
  subscription is explicit opt-in and authoritative over a present key (text +
  imagery, one policy).
- **WORLD-GROWTH** — host build wired into the turn loop (`_growth_attempt`),
  consuming the shipped **ATOMIC-ACTIVATION-V1** envelope live.
- **valid_from teleport fix** — extracted relocations stamp at the turn, not t=0.
- **hostcontrol sweep** — the conflicted-read (stale-arc) telemetry now covers the
  whole `arc:` host-control class, centralized in `construct/hostcontrol.py`
  (pbeo Item 1).
- **pbeo hygiene** — cohort schema self-consistency guard
  (`tests/test_cohort_schemas.py`); the nudge `confidence` is named a model
  **self-report** at consumption (`_model_self_report`, not a measurement).

## 🔎 Pattern-buffer adoption audit (2026-07-29) — surface is current

A full sweep of pattern-buffer's shipped shapes vs Construct's consumption found
**nothing that must be adopted before the buttoned-up state.** The parked
decisions still hold:
- **Adopt-later, correctly parked:** `SOURCE-IDENTITY-V1` (Construct has zero
  reachable exposure — single-doc worlds); `confidence()` / multi-frame confidence
  (trigger met, but no host need *and* a known backwards corroboration gradient);
  `EXACT-DECIMAL`, `MCP-WRAPPER`, `TRACKING-MODE` (not needed for an in-process,
  fiction-mode host); AWARENESS-READS `correlated=`/`features=` flags,
  `state_union()`/`correlations()`, `features()`/`composition()` reads (no current
  call for them).
- **The one shipped-but-relevant partial → roadmap:** `MOVED-EVENT-V1` endpoints
  are consumed, but `in_transit()` + the six additive `events()` keys are not.

## 🧩 Small remaining slices (below the headline)

- **MOVED-EVENT-V1 transit read** — add origin/destination/manner/valid_to (+
  `origin_bound`/`destination_bound`) to the adapter `EventRow` and consume
  `in_transit()`. Engine shipped; spec-locked, self-contained. See
  `moved-event-host-consumption` (memory) + `specs/MOVED-EVENT-V1.md`.
- **WORLD-GROWTH acceptance + latency** — mechanism is built; run the
  displaced-Ironhold probe (`scripts/displaced_ch2_probe.py`) as an acceptance
  pass and decompose the 400–450s turns.

## ⏳ Passive review gates (self-reporting, no action)

- **cr** — review of the hostcontrol slice is queued (delivers on cr's next launch).
- **pbr** — ATOMIC-ACTIVATION verdicted **RED (2026-07-29), but implementation
  fidelity only** — the r11 public surface Construct consumes does NOT move (F1 is
  an internal poison-gate repair; F2 tightens Python to reject shapes the schema
  already excluded, and our grep confirmed we emit none). No host action; pb is
  fixing both and notifies us when it goes GREEN. MOVED-EVENT-V1 still under review.
