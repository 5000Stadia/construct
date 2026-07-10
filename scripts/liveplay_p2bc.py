"""LIVE-PLAY acceptance script for Living-World Generator P2b (opportunistic) + P2c
(ambient), per spec §F in docs/design/LIVING-WORLD-GENERATOR-P2.md.

World: a hand-authored ENDLESS-mode frontier trading-post. Cast:
  person:keeper  — the player, the post's keeper
  person:brennah — a trapper with drive/fear (spined NPC)
  person:oskar   — the company factor (spined NPC)
Main arc: "bring the post through the season" (SETUP phase initially).

Four probes (§F):
  P2b: player materially touches Brennah → opportunistic mint expected.
  Contemplation: 5+ quiet turns → NO mint (diegetic-time ruling holds).
  P2c: advance diegetic clock past AMBIENT_QUIET_MIN with NO development →
       ambient mint expected.
  Right-of-way: force main arc to CRISIS/CLIMAX → NO mint, NO receipts.

Run with --dry-run to author the world, exercise all reads, and exit without
opening a real provider session (no Codex calls).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from patternbuffer import World
from patternbuffer.testing import StubModel, rule_classifier_fallback

from construct.arc import io as arc_io
from construct.arc.conditions import InFrame, StateIs, TurnsQuiet
from construct.arc.executor import PLOT, SESSION, turn_time
from construct.arc.generator import (
    AMBIENT_QUIET_MIN,
    _last_development_min,
    _mark_development,
    generate_ambient,
    generate_opportunistic,
    main_at_peak,
    salient_moments,
)
from construct.arc.grammar import (
    Arc, Beat, Clock, ConclusionShape, Phase, Rung, Weight,
)
from construct.clock import commit_elapsed, read_clock
from construct.semantics import attribute_default

# --------------------------------------------------------------------------- #
# Entity ids for the trading-post world
# --------------------------------------------------------------------------- #
KEEPER   = "person:keeper"    # the player
BRENNAH  = "person:brennah"   # trapper; spined NPC (drive + fear)
OSKAR    = "person:oskar"     # factor; spined NPC
POST     = "place:post"       # the frontier trading-post
STORES   = "place:stores"     # the back stores
FACT_DEBT = "fact:debt"       # Brennah's late husband's debt — the world tension
SEASON   = "fact:season"      # the season passing

KF = f"knows:{KEEPER}"       # the player's knowledge frame

STYLE = (
    "Frontier realism, laconic and weather-worn. Short sentences, the smell of "
    "pine tar and dried meat, debts owed in silence. Wonder lives in endurance, "
    "not spectacle."
)
INTRO = (
    "The first freeze came three days early. The company factor arrived yesterday "
    "with a sealed letter and an expression like bad news. You are the keeper of "
    "the post — every account, every bale, every soul who crosses that threshold "
    "is yours to reckon with."
)


# --------------------------------------------------------------------------- #
# World authoring
# --------------------------------------------------------------------------- #

def author_world(path: Path) -> None:
    """Hand-author the trading-post world with full structural semantics, arcs,
    and portfolio — exactly as liveplay_p2.py's author_world does."""
    rule = rule_classifier_fallback()

    def fallback(prompt, schema):
        if prompt.startswith("Classify the lifetime"):
            return rule(prompt, schema)
        return {"items": []}

    w = World(path, world_id="w:post", model=StubModel(fallback=fallback),
              stance="fiction", title="The Frontier Post",
              attribute_default=attribute_default)
    w.ingestor.cursor.advance(1.0)
    w.ingest_structured([
        # Places
        {"entity": POST,  "attribute": "kind",  "value": "place",     "timeless": True},
        {"entity": POST,  "attribute": "description",
         "value": "A low-roofed log post at the edge of the territories, "
                  "two stoves and a long counter, snow already on the eaves.",
         "timeless": True},
        {"entity": STORES, "attribute": "kind", "value": "place",     "timeless": True},
        {"entity": STORES, "attribute": "description",
         "value": "Shelves of salt-meat, flour, and trade goods; the ledger "
                  "lives here on its iron hook.", "timeless": True},
        # People
        {"entity": KEEPER,  "attribute": "kind",  "value": "person",  "timeless": True},
        {"entity": KEEPER,  "attribute": "in",    "value": POST},
        {"entity": KEEPER,  "attribute": "role",  "value": "post keeper", "timeless": True},
        {"entity": BRENNAH, "attribute": "kind",  "value": "person",  "timeless": True},
        {"entity": BRENNAH, "attribute": "in",    "value": POST},
        {"entity": BRENNAH, "attribute": "role",  "value": "trapper", "timeless": True},
        {"entity": BRENNAH, "attribute": "drive", "value": "drive:settle_husbands_debt"},
        {"entity": BRENNAH, "attribute": "fear",  "value": "fear:losing_the_trapping_ground"},
        {"entity": OSKAR,   "attribute": "kind",  "value": "person",  "timeless": True},
        {"entity": OSKAR,   "attribute": "in",    "value": POST},
        {"entity": OSKAR,   "attribute": "role",  "value": "company factor", "timeless": True},
        {"entity": OSKAR,   "attribute": "drive", "value": "drive:keep_ledger_clean"},
        {"entity": OSKAR,   "attribute": "fear",  "value": "fear:company_audit"},
        # World facts / propositions
        {"entity": FACT_DEBT, "attribute": "kind",   "value": "proposition", "timeless": True},
        {"entity": FACT_DEBT, "attribute": "holder", "value": BRENNAH},
        {"entity": FACT_DEBT, "attribute": "amount", "value": "three seasons of credit"},
        {"entity": SEASON,    "attribute": "kind",   "value": "proposition", "timeless": True},
        {"entity": SEASON,    "attribute": "phase",  "value": "onset_of_winter"},
    ])

    # ---- MAIN arc: survive the season (ENDLESS mode — open destination) ----
    # The arc climax is gated on the keeper learning the season is safe to trade
    # through. We set climax_ready_k=1 so we can force CRISIS easily by marking
    # the one climax-ready beat achieved.
    main_beat = Beat(
        "beat:season_turns",
        Phase.CLIMAX,
        Weight.REQUIRED,
        achievable_via=InFrame(KF, SEASON, "phase", "safe_to_trade"),
    )
    # A second beat that gates CRISIS: the keeper recognises the debt problem.
    crisis_beat = Beat(
        "beat:debt_known",
        Phase.CRISIS,
        Weight.REQUIRED,
        achievable_via=InFrame(KF, FACT_DEBT, "amount", "three seasons of credit"),
    )
    # Refusal clock — long fuse (15 quiet turns) since this is endless mode.
    main_refusal = Clock(
        "clock:refusal_main",
        TurnsQuiet(15),
        effects=({"entity": "event:post_closes", "attribute": "kind",
                  "value": "refusal_conclusion"},),
        bound_to="arc:main",
        rung=Rung.REFUSAL,
    )
    main_shape = ConclusionShape(
        "shape:main", "desire_at_cost",
        (KEEPER, "drive:endure", "fear:isolation"),
        world_condition=InFrame(KF, SEASON, "phase", "safe_to_trade"),
        premise=StateIs(KEEPER, "kind", "person"),
        refusal_variant_id="shape:refused_main",
    )
    # climax_ready_k=1 means ONE climax-ready beat achieved → CLIMAX phase.
    main = Arc(
        "arc:main", KEEPER, main_shape,
        (crisis_beat, main_beat),
        (),
        main_refusal,
        1,                            # climax_ready_k
        ("beat:season_turns",),       # climax_ready_beats
        {Phase.SETUP: 5, Phase.RISING: 6, Phase.CRISIS: 3,
         Phase.CLIMAX: 2, Phase.FALLING: 2},
    )

    items = arc_io.arc_to_items(main) + arc_io.index_items(main)
    items += arc_io.portfolio_items(["arc:main"], main_arc_id="arc:main")
    w.porcelain.ingest_structured(items)
    w.porcelain.ingest_structured(
        [{"entity": "event:turn_0", "attribute": "kind", "value": "turn",
          "valid_from": turn_time(0)}],
        frame=SESSION,
    )
    w.close()

    path.with_suffix(".meta.json").write_text(json.dumps({
        "title":        "The Frontier Post",
        "protagonist":  KEEPER,
        "stance":       "fiction",
        "mode":         "pure",
        "scenario_mode": "endless",      # P2c only fires in endless mode
        "style":        STYLE,
        "intro":        INTRO,
        "goal_statement": "bring the post through the season",
        "arc_scope":    [KEEPER, BRENNAH, OSKAR, POST, STORES, FACT_DEBT, SEASON],
        "main_arc":     "arc:main",
        "arc_ids":      ["arc:main"],
    }, indent=2))


# --------------------------------------------------------------------------- #
# World interventions (deterministic between-turn writes)
# --------------------------------------------------------------------------- #

def _log_player_evidence(world, turn, w) -> None:
    """Acceptance evidence (Cx amendment): log the Brennah-touching rows committed
    in this turn's window so a silent Probe 1 is diagnosable — a valid spine-touch
    trial (row present, mint expected) vs extraction variance (no row committed)."""
    from construct.adapter import frame_facts
    lo, hi = turn_time(turn) - 0.5, turn_time(turn) + 0.5
    rows = [r for r in frame_facts(world, "canon")
            if r.valid_from is not None and lo < r.valid_from < hi
            and ("brennah" in str(r.entity).lower() or "brennah" in str(r.value).lower())]
    w(f"> _player-commit evidence (turn {turn}): "
      f"{[(r.entity, r.attribute, str(r.value)[:30]) for r in rows] or 'NO Brennah-touching rows committed'}_")
    w()


def force_main_arc_to_crisis(world) -> None:
    """Force the main arc into CRISIS: achieve the crisis-gating beat (beat:debt_known).
    The player learning the debt amount satisfies InFrame(KF, FACT_DEBT, 'amount', ...).
    We write the beat's achieved status directly (same pattern as the tests use for
    test_main_at_peak_climax_returns_true)."""
    world.porcelain.ingest_structured([
        {"entity": "beat:debt_known", "attribute": "status", "value": "achieved",
         "valid_from": turn_time(10)},
    ], frame=PLOT)


def force_main_arc_to_climax(world) -> None:
    """Force the main arc into CLIMAX: achieve the climax_ready beat (beat:season_turns).
    With climax_ready_k=1 this is enough to push into CLIMAX via current_phase."""
    world.porcelain.ingest_structured([
        {"entity": "beat:season_turns", "attribute": "status", "value": "achieved",
         "valid_from": turn_time(11)},
    ], frame=PLOT)


# --------------------------------------------------------------------------- #
# Provider stubs for the dry-run
# --------------------------------------------------------------------------- #

class _DryRunProvider:
    """Minimal provider for dry-run: raises if called, so we can confirm no real
    model calls happen in the audit reads."""
    async def complete(self, *a, **k):
        raise AssertionError("DryRunProvider called — review should not fire model calls")


# --------------------------------------------------------------------------- #
# Dry-run: author the world, exercise all probe reads, print the audit section
# --------------------------------------------------------------------------- #

def dry_run(path: Path) -> None:
    """Author the world and exercise all reads the four probes need, without
    opening a Session or calling the provider. Prints the 'State at close'
    audit block to stdout."""
    from construct.adapter import PorcelainWorldReads, frame_facts
    from construct.arc.executor import current_phase

    print("=== DRY-RUN: world authoring ===")
    if path.exists():
        path.unlink()
    path.with_suffix(".meta.json").unlink(missing_ok=True)
    author_world(path)
    print(f"  world written: {path}")
    meta = json.loads(path.with_suffix(".meta.json").read_text())
    print(f"  meta.scenario_mode = {meta['scenario_mode']!r}")

    # Reopen the world (as production does) to exercise the reads.
    rule = rule_classifier_fallback()
    w = World(path, world_id="w:post", model=StubModel(
        fallback=lambda p, s: rule(p, s) if p.startswith("Classify") else {"items": []}),
        stance="fiction", attribute_default=attribute_default)

    reads = PorcelainWorldReads(w)
    arcs = arc_io.portfolio_from_frame(reads)
    by_id = {a.arc_id: a for a in arcs}
    main = by_id["arc:main"]

    print("\n=== DRY-RUN: probe reads ===")

    # --- Probe 1 reads: salient_moments with a spine-touch -------------------
    print("\n[Probe 1 — P2b: spine-touch salience]")
    # Simulate the window fact_rows from committing a row touching Brennah.
    window_facts = [
        {"entity": BRENNAH, "attribute": "debt_discussed", "value": "yes"},
    ]
    spined = {BRENNAH, OSKAR}
    prior_kinds: set[str] = {"turn", "player_action"}
    moments = salient_moments(window_facts, [], prior_kinds, spined)
    print(f"  salient_moments result: {moments}")
    assert moments, "spine-touch must produce salient moments"
    print("  PASS: spine-touch is salient")

    # --- Probe 2 reads: contemplation turns → NOT salient -------------------
    print("\n[Probe 2 — Contemplation: no new facts, no new event kinds]")
    # Pure 'look' turns: no fact rows touching spined NPCs, no new event kinds.
    contemplate_facts: list[dict] = []       # nothing committed
    contemplate_events: list = []            # no interesting events
    non_salient = salient_moments(
        contemplate_facts, contemplate_events, prior_kinds, spined)
    print(f"  salient_moments (contemplation): {non_salient}")
    assert non_salient == [], "contemplation turns must NOT be salient"
    print("  PASS: contemplation turns are not salient — no mint expected")

    # --- Probe 3 reads: diegetic clock past AMBIENT_QUIET_MIN ---------------
    print("\n[Probe 3 — P2c: ambient diegetic threshold]")
    minutes_before = read_clock(w).minutes
    print(f"  clock before advance: {minutes_before} minutes")
    # Advance by AMBIENT_QUIET_MIN + 10 to exceed the threshold.
    advance_delta = int(AMBIENT_QUIET_MIN) + 10
    commit_elapsed(w, advance_delta)
    minutes_after = read_clock(w).minutes
    print(f"  clock after advance ({advance_delta} min): {minutes_after} minutes")
    reads2 = PorcelainWorldReads(w)
    # Seed the baseline (write-once).
    baseline_before = _last_development_min(w, reads2, float(minutes_before), turn=1)
    print(f"  last_development_min baseline: {baseline_before}")
    reads3 = PorcelainWorldReads(w)
    last_dev = _last_development_min(w, reads3, float(minutes_after), turn=2)
    delta_minutes = float(minutes_after) - last_dev
    print(f"  diegetic delta since last development: {delta_minutes} minutes")
    print(f"  AMBIENT_QUIET_MIN threshold: {AMBIENT_QUIET_MIN}")
    assert delta_minutes >= AMBIENT_QUIET_MIN, (
        f"ambient threshold not crossed: {delta_minutes} < {AMBIENT_QUIET_MIN}")
    print("  PASS: ambient threshold is crossed — ambient trigger would fire")

    # --- Probe 4 reads: main arc at peak (CRISIS/CLIMAX) → right-of-way -----
    print("\n[Probe 4 — Right-of-way: main arc at CRISIS/CLIMAX]")
    phase_before = current_phase(reads, main)
    print(f"  phase before forcing crisis: {phase_before}")
    assert phase_before not in (Phase.CRISIS, Phase.CLIMAX), (
        f"unexpected: main arc already at peak ({phase_before})")
    force_main_arc_to_crisis(w)
    force_main_arc_to_climax(w)
    reads4 = PorcelainWorldReads(w)
    main2 = next(a for a in arc_io.portfolio_from_frame(reads4) if a.arc_id == "arc:main")
    phase_after = current_phase(reads4, main2)
    print(f"  phase after forcing crisis+climax beats: {phase_after}")
    at_peak = main_at_peak(reads4, main2)
    print(f"  main_at_peak: {at_peak}")
    assert at_peak, "main arc must be at peak after forcing beats"
    print("  PASS: main arc is at peak — right-of-way would suppress all mints")

    # --- Portfolio and session state audit ----------------------------------
    print("\n=== State at close (audit) ===")
    ids = arc_io.arc_ids_from_frame(reads4)
    gen_ids = [a for a in ids if a.startswith("arc:gen_")]
    print(f"portfolio arc ids: {ids}")
    print(f"generated arc ids (arc:gen_*): {gen_ids}")
    for gid in gen_ids:
        prov = w.porcelain.state(gid, "generated_from", frame=PLOT)
        depth = w.porcelain.state(gid, "gen_depth", frame=PLOT)
        prov_val = (prov.get("fact") or {}).get("value")
        depth_val = (depth.get("fact") or {}).get("value")
        print(f"  generated {gid}: from={prov_val} depth={depth_val}")
    attempts = [e.event_id for e in reads4.events(kind="generation_attempt", frame=SESSION)]
    declines = [e.event_id for e in reads4.events(kind="generation_declined", frame=SESSION)]
    print(f"generation_attempt receipts (dry-run: expect empty): {attempts}")
    print(f"generation_declined receipts (dry-run: expect empty): {declines}")
    # session:ambient row check
    ambient_raw = w.porcelain.state("session:ambient", "last_development_min", frame=SESSION)
    print(f"session:ambient/last_development_min: {ambient_raw}")
    # Membrane: generated bookkeeping must NOT appear in canon.
    for gid in gen_ids:
        cst = w.porcelain.state(gid, "generated")  # canon read
        print(f"MEMBRANE — {gid}.generated in canon: {cst.get('status')} (expect not 'known')")

    # Verify the meta reads correctly for endless mode.
    assert meta["scenario_mode"] == "endless", "scenario_mode must be 'endless' for P2c"
    print("\nAll dry-run assertions PASS.")
    w.close()


# --------------------------------------------------------------------------- #
# Live main — the full logged probe run (costs real Codex calls)
# --------------------------------------------------------------------------- #

def main() -> None:
    from construct import Session
    from construct.adapter import PorcelainWorldReads
    from construct.provider import CodexProvider

    worlds = Path("worlds"); worlds.mkdir(exist_ok=True)
    logs   = Path("logs");   logs.mkdir(exist_ok=True)
    ts   = os.environ.get("LIVEPLAY_TS", "manual")
    log  = logs / f"liveplay-p2bc-{ts}.md"
    spath = worlds / "post.world"

    # Clean any prior run.
    if spath.exists():
        spath.unlink()
    spath.with_suffix(".meta.json").unlink(missing_ok=True)
    for slot in worlds.glob("post.play*.world"):
        slot.unlink()

    author_world(spath)

    out = log.open("w")

    def w(line=""):
        out.write(line + "\n"); out.flush()

    w("# Live-play — Living-World Generator P2b + P2c (a FRONTIER TRADING-POST)")
    w()
    w("An endless frontier world (the keeper of a remote trading-post). Cast: two "
      "spined NPCs — Brennah (trapper with a debt drive) and Oskar (the company "
      "factor). Main arc: bring the post through the season.")
    w()
    w("**Four probes:**  "
      "P2b (opportunistic — spine-touch), "
      "Contemplation (no mint expected), "
      "P2c (ambient diegetic threshold), "
      "Right-of-way (main at CRISIS/CLIMAX — silent).")
    w()

    provider = CodexProvider()
    s = Session.open("post", player_id="founder", fresh=True, provider=provider)

    w("## Opening")
    w("```")
    w(s.opening())
    w("```")
    w()

    def play(n, text, note=None):
        if note:
            w(f"> _{note}_")
            w()
        w(f"### Turn {n}")
        w(f"**You:** {text}")
        w()
        reply = s.turn(text)
        w(f"**Narrator:** {reply.prose}")
        w()
        t = reply.trace
        if t:
            w(f"`lifecycle={t.lifecycle}` · `arc_fallout={t.arc_fallout}` · "
              f"`generated={t.generated}` · `beats_closed={t.beats_closed}` · "
              f"`ended={reply.ended}`")
        else:
            w(f"(turn did not complete: ok={reply.ok})")
        w()
        return reply

    try:
        # ---- Probe 1: P2b — player touches Brennah -------------------------
        w("## Probe 1 — P2b: Player materially touches Brennah (spine-touch)")
        w()
        w("Expectation: within `GEN_COOLDOWN` turns after the spine-touch, a new "
          "`arc:gen_*` should appear with `generated_from=player_delta:<n>` and "
          "`gen_depth=0`.")
        w()
        play(1, "I take stock of the stores before anyone arrives.",
             note="An ordinary first turn — no NPC touch yet.")
        play(2, "I take Brennah's folded tally out of her hands, spread it flat "
                "on the counter between us, and press my finger to her first line "
                "of credit.",
             note="A PHYSICAL player action with Brennah as the acted-on participant "
                  "(Cx acceptance amendment): the player-action extraction should "
                  "commit a Brennah-touching row in the CONFIRMED player batch — the "
                  "only fact source the final salience gate consumes. No direct world "
                  "writes; the trial stands or falls on the real channel.")
        _log_player_evidence(s._world, 2, w)
        play(3, "I put the flour ledger into Brennah's hands and close her fingers "
                "around it.",
             note="Second physical Brennah-touch — within the GEN_COOLDOWN window; a "
                  "second independent trial in case turn 2's extraction missed.")
        _log_player_evidence(s._world, 3, w)
        play(4, "I close the ledger and pour two cups of coffee.")

        # ---- Probe 2: Contemplation — 5 quiet turns -------------------------
        w("## Probe 2 — Contemplation: Five quiet turns (diegetic-time ruling)")
        w()
        w("Expectation: no `generation_attempt` or `generation_declined` receipts in "
          "this span. Thirty contemplation turns = 5 in-world minutes — the world "
          "stays quiet (the diegetic-time ruling holds).")
        w()
        for i, text in enumerate([
            "I look out the window at the tree-line.",
            "I think about the winter ahead.",
            "I listen to the stoves.",
            "I run my hand along the counter.",
            "I consider the accounts in my head.",
        ], start=5):
            play(i, text, note="Contemplation turn." if i == 5 else None)

        # ---- Probe 3: P2c — advance diegetic clock past AMBIENT_QUIET_MIN --
        w("## Probe 3 — P2c: Ambient trigger (diegetic half-day passes)")
        w()
        w(f"Advancing the diegetic clock by {int(AMBIENT_QUIET_MIN) + 30} minutes "
          f"(past the `AMBIENT_QUIET_MIN={AMBIENT_QUIET_MIN}` threshold) directly — "
          "the harness-side equivalent of 'the day passes'.")
        w()
        commit_elapsed(s._world, int(AMBIENT_QUIET_MIN) + 30)
        clock_now = read_clock(s._world)
        w(f"> _Clock advanced to {clock_now.minutes} minutes (Day {clock_now.day}, "
          f"{clock_now.phase})._")
        w()
        w("Expectation: the next quiet turn fires the ambient trigger "
          "(`generated_from=ambient:<n>`, `gen_depth=0`).")
        w()
        play(10, "I step outside and look at the sky.",
             note="First turn after the quiet half-day passes — ambient trigger fires.")

        # ---- Probe 4: Right-of-way — main arc at CRISIS/CLIMAX -------------
        w("## Probe 4 — Right-of-way: Main arc forced to CRISIS/CLIMAX")
        w()
        w("Forcing both beats achieved to push into CLIMAX. Then touching Brennah "
          "again — a normally-salient action. Expectation: ZERO new `arc:gen_*`, "
          "ZERO `generation_attempt`/`generation_declined` receipts this turn "
          "(right-of-way is SILENT).")
        w()
        force_main_arc_to_crisis(s._world)
        force_main_arc_to_climax(s._world)
        play(11, "I confront Brennah about the final reckoning.",
             note="Main arc at CLIMAX — right-of-way gate must suppress the DM "
                  "entirely (no receipt, no mint).")

    finally:
        w("## State at close")
        w("```")
        reads = PorcelainWorldReads(s._world)
        p = s._world.porcelain
        ids = arc_io.arc_ids_from_frame(reads)
        w(f"portfolio arc ids: {ids}")
        gen_ids = [a for a in ids if a.startswith("arc:gen_")]
        for gid in gen_ids:
            prov = p.state(gid, "generated_from", frame=PLOT)
            depth = p.state(gid, "gen_depth", frame=PLOT)
            w(f"  generated {gid}: from={prov.get('fact', {}).get('value')} "
              f"depth={depth.get('fact', {}).get('value')}")
        attempts = [e.event_id for e in reads.events(kind="generation_attempt", frame=SESSION)]
        declines = [e.event_id for e in reads.events(kind="generation_declined", frame=SESSION)]
        w(f"generation_attempt receipts: {attempts}")
        w(f"generation_declined receipts: {declines}")
        # session:ambient bookkeeping
        ambient_raw = p.state("session:ambient", "last_development_min", frame=SESSION)
        w(f"session:ambient/last_development_min: {ambient_raw}")
        clock_final = read_clock(s._world)
        w(f"diegetic clock at close: {clock_final.minutes} min (Day {clock_final.day}, "
          f"{clock_final.phase})")
        # Membrane: generator bookkeeping must NOT appear in canon.
        for gid in gen_ids:
            cst = p.state(gid, "generated")  # canon read
            w(f"MEMBRANE — {gid}.generated in canon: {cst.get('status')} "
              f"(expect not 'known')")
        w("```")
        s.close()

    out.close()
    print(str(log))


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    if "--dry-run" in sys.argv:
        worlds = Path("worlds")
        worlds.mkdir(exist_ok=True)
        dry_run(worlds / "post_dryrun.world")
    else:
        main()
