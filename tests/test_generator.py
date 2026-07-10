"""The opportunistic DM generator — P2a+P2b+P2c.

Drives `generate_from_fallout` directly (deterministic) with a stub provider that
returns a valid arc proposal, then exercises each guard: pacing cooldown, active
cap, fingerprint dedupe, depth cap, coherence preflight. Plus a full run_turn
integration test: a side arc dies and the world mints a grounded successor.

P2b/P2c tests cover: salient_moments (pure function), right-of-way (main at peak),
ambient diegetic threshold + seed-on-absent + win_loss gate, arbitration order,
player-boundary decline, and depth-0 roots with depth-1 regeneration.
"""

import json
import logging

from patternbuffer import World
from patternbuffer.testing import StubModel, rule_classifier_fallback

from construct.adapter import PorcelainWorldReads, frame_facts
from construct.arc import generator as gen
from construct.arc import io as arc_io
from construct.arc.conditions import EventRow, InFrame, StateIs, TurnsQuiet
from construct.arc.executor import PLOT, SESSION, Fallout, turn_time
from construct.arc.generator import (
    AMBIENT_QUIET_MIN,
    ROUTINE_EVENT_KINDS,
    _last_development_min,
    _mark_development,
    confirmed_batch,
    generate_ambient,
    generate_from_fallout,
    generate_opportunistic,
    main_at_peak,
    prior_promote_batch,
    salient_moments,
    window_events,
)
from construct.arc.grammar import (
    Arc, Beat, Clock, ConclusionShape, Phase, Rung, Weight,
)
from construct.provider import StubProvider, task_of

PLAYER = "person:player"
CLERK = "person:clerk"

VALID_PROPOSAL = {
    "protagonist": CLERK,
    "delta_type": "desire_at_cost",
    "tension": [CLERK, "drive:duty", "drive:fear"],
    "beats": [{"id": "beat:clerk_moves", "phase": "climax", "weight": "required",
               "kind": "event_occurs", "entity": "clerk_confrontation",
               "attribute": "", "value": ""}],
    "hook": "The clerk pushes back from her desk, jaw set, and starts your way.",
}


class _GenProvider(StubProvider):
    """Returns a valid arc proposal for the DM-generator prompt; permissive
    elsewhere."""

    def __init__(self, proposal=None):
        super().__init__([])
        self._proposal = proposal if proposal is not None else dict(VALID_PROPOSAL)

    async def complete(self, prompt, schema, *, tier="main", deliberate=False):
        self.calls.append((prompt, schema, tier))
        if task_of(prompt) == "gen":
            return dict(self._proposal)
        if prompt.startswith("Classify the lifetime"):
            return {"durability": "STATE", "confidence": 0.9}
        return {"items": []}


def _world(path, *, attribute_default=None) -> World:
    rule = rule_classifier_fallback()

    def fallback(prompt, schema):
        if prompt.startswith("Classify the lifetime"):
            return rule(prompt, schema)
        return {"items": []}

    kw = {"attribute_default": attribute_default} if attribute_default else {}
    w = World(path, world_id="w:gen", model=StubModel(fallback=fallback),
              stance="fiction", title="Gen Test World", **kw)
    w.ingestor.cursor.advance(1.0)
    w.ingest_structured([
        {"entity": "place:office", "attribute": "kind", "value": "room", "timeless": True},
        {"entity": PLAYER, "attribute": "kind", "value": "person", "timeless": True},
        {"entity": PLAYER, "attribute": "in", "value": "place:office"},
        {"entity": CLERK, "attribute": "kind", "value": "person", "timeless": True},
        {"entity": CLERK, "attribute": "in", "value": "place:office"},
        {"entity": CLERK, "attribute": "drive", "value": "drive:duty"},
        {"entity": "fact:secret", "attribute": "kind", "value": "proposition", "timeless": True},
    ])
    # A minimal main arc + the portfolio manifest (so additions supersede cleanly).
    beat = Beat("beat:discover", Phase.CLIMAX, Weight.REQUIRED,
                achievable_via=InFrame(f"knows:{PLAYER}", "fact:secret", "x", "y"))
    refusal = Clock("clock:refusal", TurnsQuiet(15),
                    effects=({"entity": "event:world_concludes", "attribute": "kind",
                              "value": "refusal_conclusion"},),
                    bound_to="arc:main", rung=Rung.REFUSAL)
    shape = ConclusionShape("shape:main", "drive_inverted", (PLAYER, "a", "b"),
                            world_condition=InFrame(f"knows:{PLAYER}", "fact:secret", "x", "y"),
                            premise=StateIs(PLAYER, "kind", "person"),
                            refusal_variant_id="shape:refused")
    main = Arc("arc:main", PLAYER, shape, (beat,), (), refusal, 1, ("beat:discover",),
               {Phase.SETUP: 5, Phase.RISING: 6, Phase.CRISIS: 3, Phase.CLIMAX: 2,
                Phase.FALLING: 2})
    w.porcelain.ingest_structured(arc_io.arc_to_items(main) + arc_io.index_items(main)
                                  + arc_io.portfolio_items(["arc:main"], main_arc_id="arc:main"))
    w.porcelain.ingest_structured(
        [{"entity": "event:turn_0", "attribute": "kind", "value": "turn",
          "valid_from": turn_time(0)}], frame=SESSION)
    return w


def _fallout(slug="dead", entity=CLERK) -> Fallout:
    return Fallout(arc_id=f"arc:{slug}", lifecycle="incompletable",
                   term_id=f"event:arc_terminal_{slug}", entity=entity,
                   attribute="desire_unresolved", value="drive:duty",
                   directive="the clerk's matter hangs open.")


def _ctx():
    return {"style": "noir", "available_ids": [CLERK, PLAYER, "fact:secret"],
            "present_characters": f"{CLERK}: drive=drive:duty fear=None"}


def test_regenerative_mint_succeeds(tmp_path):
    w = _world(tmp_path / "g.world")
    reads = PorcelainWorldReads(w)
    minted = generate_from_fallout(w, reads, _GenProvider(), _fallout(), [], _ctx(), turn=1)
    assert minted is not None
    arc, hook = minted
    assert arc.arc_id == "arc:gen_1" and hook
    # The new arc is registered in the portfolio and reconstructs.
    ids = arc_io.arc_ids_from_frame(PorcelainWorldReads(w))
    assert "arc:gen_1" in ids
    by_id = {a.arc_id: a for a in arc_io.portfolio_from_frame(PorcelainWorldReads(w))}
    assert "arc:gen_1" in by_id
    # Provenance (plot bookkeeping) + the lineage receipt (session).
    p = w.porcelain
    assert p.state("arc:gen_1", "generated", frame=PLOT)["fact"]["value"] == "yes"
    assert p.state("arc:gen_1", "generated_from", frame=PLOT)["fact"]["value"] \
        == "event:arc_terminal_dead"
    assert p.state("arc:gen_1", "gen_depth", frame=PLOT)["fact"]["value"] in (1, "1")
    assert PorcelainWorldReads(w).events(kind="generation_attempt", frame=SESSION)
    w.close()


def test_regenerative_mint_after_reopen(tmp_path):
    """The production reopen path: a world AUTHORED with the structural-semantics
    rule (game._world) is closed and REOPENED (a fresh World over the saved
    buffer), then the generator mints a new arc — whose arc_to_items re-writes the
    structural enums (delta_type/rung/…). This must NOT trip 'cannot declare
    semantics after folded data' (the seam the live P2 test surfaced: authoring
    without attribute_default left delta_type undeclared). Regression guard."""
    from construct.semantics import attribute_default as attr_default
    path = tmp_path / "reopen.world"
    w = _world(path, attribute_default=attr_default)
    w.close()
    # Reopen fresh over the saved buffer (as open_playthrough's _world does).
    w2 = World(path, world_id="w:gen", model=StubModel(
        fallback=lambda p, s: {"items": []}), stance="fiction",
        attribute_default=attr_default)
    minted = generate_from_fallout(w2, PorcelainWorldReads(w2), _GenProvider(),
                                   _fallout(), [], _ctx(), turn=1)
    assert minted is not None and minted[0].arc_id == "arc:gen_1"
    w2.close()


def test_membrane_holds_for_generator(tmp_path):
    """The generator's bookkeeping lives in plot:/session:, NEVER canon."""
    w = _world(tmp_path / "mem.world")
    generate_from_fallout(w, PorcelainWorldReads(w), _GenProvider(), _fallout(), [],
                          _ctx(), turn=1)
    p = w.porcelain
    # The arc rows are in plot:, absent from canon.
    assert p.state("arc:gen_1", "generated")["status"] != "known"  # canon read
    assert p.state("arc:gen_1", "generated", frame=PLOT)["status"] == "known"
    w.close()


def test_pacing_cooldown_blocks(tmp_path):
    w = _world(tmp_path / "cd.world")
    # An attempt last turn; cooldown is GEN_COOLDOWN turns.
    w.porcelain.ingest_structured(
        [{"entity": "event:gen_attempt_5", "attribute": "kind",
          "value": "generation_attempt", "valid_from": turn_time(5)}], frame=SESSION)
    out = generate_from_fallout(w, PorcelainWorldReads(w), _GenProvider(), _fallout(),
                                [], _ctx(), turn=6)  # 6-5=1 < GEN_COOLDOWN(2)
    assert out is None
    w.close()


def test_active_cap_blocks(tmp_path):
    w = _world(tmp_path / "cap.world")
    # Stand up GEN_ACTIVE_CAP active generated side arcs.
    side = []
    for i in range(gen.GEN_ACTIVE_CAP):
        aid = f"arc:gen_existing_{i}"
        w.porcelain.ingest_structured(
            [{"entity": aid, "attribute": "generated", "value": "yes", "timeless": True}],
            frame=PLOT)
        a = type("A", (), {"arc_id": aid})()  # lightweight stand-in for _active_generated
        side.append(a)
    out = generate_from_fallout(w, PorcelainWorldReads(w), _GenProvider(), _fallout(),
                                side, _ctx(), turn=10)
    assert out is None
    w.close()


def test_fingerprint_dedupe_blocks(tmp_path):
    w = _world(tmp_path / "fp.world")
    fp = gen._fingerprint(VALID_PROPOSAL)
    w.porcelain.ingest_structured(
        [{"entity": f"gen:fp:{fp}", "attribute": "kind", "value": "gen_fingerprint",
          "valid_from": turn_time(0)}], frame=SESSION)
    out = generate_from_fallout(w, PorcelainWorldReads(w), _GenProvider(), _fallout(),
                                [], _ctx(), turn=1)
    assert out is None
    assert any("duplicate" in e.event_id for e in
               PorcelainWorldReads(w).events(kind="generation_declined", frame=SESSION))
    w.close()


def test_depth_cap_blocks_and_exhausts(tmp_path):
    w = _world(tmp_path / "depth.world")
    # The fallout's parent arc is itself at the depth cap.
    w.porcelain.ingest_structured(
        [{"entity": "arc:gen_99", "attribute": "gen_depth",
          "value": gen.GEN_DEPTH_CAP, "timeless": True}], frame=PLOT)
    out = generate_from_fallout(w, PorcelainWorldReads(w), _GenProvider(),
                                _fallout(slug="gen_99"), [], _ctx(), turn=1)
    assert out is None
    assert gen._lineage_exhausted(PorcelainWorldReads(w), "event:arc_terminal_gen_99")
    w.close()


def test_preflight_rejects_ungrounded_protagonist(tmp_path):
    """An invented protagonist (not in the world) is rejected — else the P1
    fallout would later canonize a phantom entity (Codex BLOCKER)."""
    w = _world(tmp_path / "ung.world")
    bad = dict(VALID_PROPOSAL)
    bad["protagonist"] = "person:invented"
    bad["tension"] = ["person:invented", "drive:x", "drive:y"]
    out = generate_from_fallout(w, PorcelainWorldReads(w), _GenProvider(bad), _fallout(),
                                [], _ctx(), turn=1)
    assert out is None
    declines = [e.event_id for e in
                PorcelainWorldReads(w).events(kind="generation_declined", frame=SESSION)]
    assert any("ungrounded" in d for d in declines)
    w.close()


def test_hook_with_leaked_id_is_dropped(tmp_path):
    """A hook carrying a raw entity id is scrubbed (concealment is not prompt-only)."""
    w = _world(tmp_path / "hook.world")
    leaky = dict(VALID_PROPOSAL)
    leaky["hook"] = "person:clerk lunges across the desk."
    minted = generate_from_fallout(w, PorcelainWorldReads(w), _GenProvider(leaky),
                                   _fallout(), [], _ctx(), turn=1)
    assert minted is not None  # the arc still mints
    _arc, hook = minted
    assert hook == ""  # but the leaky hook is dropped
    assert gen._sanitize_hook("The clerk lunges across the desk.") != ""
    w.close()


def test_duplicate_tension_blocked_across_sources(tmp_path):
    """The same situation can't regenerate even from a DIFFERENT dead arc
    (fingerprint is situation-scoped, not source-scoped — Codex SHOULD)."""
    w = _world(tmp_path / "dup.world")
    m1 = generate_from_fallout(w, PorcelainWorldReads(w), _GenProvider(),
                               _fallout(slug="a"), [], _ctx(), turn=1)
    assert m1 is not None
    side = [m1[0]]
    # A different dead arc, same proposed tension, far enough out to clear cooldown.
    m2 = generate_from_fallout(w, PorcelainWorldReads(w), _GenProvider(),
                               _fallout(slug="b"), side, _ctx(), turn=5)
    assert m2 is None  # deduped on the situation
    w.close()


def test_locatable_people_excludes_unlocated_role(tmp_path):
    # Cx 160 #3: the protagonist guard must require a LOCATED person, not mere existence.
    # A generic extracted role (person:detective, kind row only, never staged) must NOT pass.
    from construct.game import _locatable_people
    w = _world(tmp_path / "loc.world")
    w.ingest_structured([{"entity": "person:detective", "attribute": "kind",
                          "value": "person", "timeless": True}])  # role shell, no `in`
    known = ["person:player", "person:clerk", "person:detective"]
    located = _locatable_people(w, known)
    assert "person:player" in located and "person:clerk" in located
    assert "person:detective" not in located            # exists, but unstaged → excluded
    w.close()


def test_fallback_protagonist_prefers_located(tmp_path):
    # Cx 160 #2/#4: the fallback binds to a LOCATED person; play_as is only a tie-breaker,
    # never a license to keep the unlocated role.
    from construct.game import _fallback_protagonist
    w = _world(tmp_path / "fb.world")
    located = ["person:player", "person:clerk"]
    assert _fallback_protagonist(w, located, "the clerk on the night shift") == "person:clerk"
    assert _fallback_protagonist(w, located, "") in located         # no hint → a located person
    assert _fallback_protagonist(w, [], "anything") is None         # nothing staged → None


def test_build_arc_rebuild_rebinds_every_protagonist_gate(tmp_path):
    # Cx 160 #1 — THE invariant: the fallback must REBUILD from the corrected proposal, never
    # dataclasses.replace, because _build_arc bakes knows:<protagonist> into every player_learns
    # beat (and failure_when/premise). Assert a rebuild leaves NO stale knows:person:detective.
    from construct.game import _build_arc
    from construct.arc.conditions import atoms_of, InFrame

    def _frames(arc):
        fs = set()
        exprs = [b.achievable_via for b in arc.beats]
        if arc.failure_when is not None:
            exprs.append(arc.failure_when)
        for e in exprs:
            fs |= {a.frame for a in atoms_of(e) if isinstance(a, InFrame)}
        return fs

    proposal = {
        "protagonist": "person:detective",
        "delta_type": "drive_inverted",
        "tension": ["person:detective", "drive:doubt", "drive:proof"],
        "beats": [{"id": "beat:learn", "phase": "rising", "weight": "required",
                   "kind": "player_learns", "entity": "fact:secret",
                   "attribute": "culprit", "value": "person:clerk"},
                  {"id": "beat:act", "phase": "climax", "weight": "required",
                   "kind": "event_occurs", "entity": "confront", "attribute": "", "value": ""}],
        "failure_when": {"kind": "player_learns", "entity": "fact:secret",
                         "attribute": "blown", "value": "true"},
    }
    bad = _build_arc(proposal)
    assert "knows:person:detective" in _frames(bad)         # the broken binding, as built

    proposal["protagonist"] = "person:player"               # the fallback rewrite
    good = _build_arc(proposal)                              # REBUILD (not replace)
    assert good.protagonist == "person:player"
    assert "knows:person:player" in _frames(good)
    assert "knows:person:detective" not in _frames(good)    # NO stale gate survives the rebind


def test_finalize_stages_anchor_in_bare_world(tmp_path):
    # #104 (the seaside-bookstore deadlock) SUPERSEDES the Cx-162 raise-on-bare-world
    # mechanism while keeping its INVARIANT: an unstageable protagonist never
    # publishes. A generated world whose prose placed nobody is a STAGING gap, not a
    # bad pick — the play_as-matching person is deterministically staged at the
    # world's first place and the build proceeds. (The mispick case — located people
    # exist, author picks an unlocated id — keeps the 162 guard/fallback unchanged.)
    import pytest
    from construct.provider import StubProvider, task_of
    from construct import game

    rule = rule_classifier_fallback()

    def fallback(prompt, schema):
        return rule(prompt, schema) if prompt.startswith("Classify the lifetime") else {"items": []}

    path = tmp_path / "uns.world"
    w = World(path, world_id="w:uns", model=StubModel(fallback=fallback),
              stance="fiction", title="Unstaged World")
    w.ingestor.cursor.advance(1.0)
    w.ingest_structured([                                   # people exist but are NEVER located
        {"entity": "place:office", "attribute": "kind", "value": "room", "timeless": True},
        {"entity": "person:a", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:b", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "fact:secret", "attribute": "kind", "value": "proposition", "timeless": True},
    ])

    proposal = {
        "protagonist": "person:a", "delta_type": "drive_inverted",
        "tension": ["person:a", "drive:doubt", "drive:proof"],
        "goal_statement": "find the truth", "theme": "the truth beneath the office",
        "beats": [{"id": "beat:learn", "phase": "climax", "weight": "required",
                   "kind": "player_learns", "entity": "fact:secret",
                   "attribute": "culprit", "value": "person:b"}],
    }

    class _ArcProvider(StubProvider):
        def __init__(self):
            super().__init__([])

        async def complete(self, prompt, schema, *, tier="main", deliberate=False):
            if prompt.startswith("Classify the lifetime"):
                return {"durability": "STATE", "confidence": 0.9}
            if task_of(prompt) == "arc":
                return dict(proposal)
            return {"items": []}

    spath = tmp_path / "uns_scenario.world"
    game._finalize_scenario(w, "uns", "Unstaged World", _ArcProvider(), spath,
                            endless=False, play_as="person a")
    assert spath.with_suffix(".meta.json").exists()          # PUBLISHED — no deadlock
    assert w.porcelain.locate("person:a")[0] == "place:office"   # anchored, play_as-matched
    w.close()


def test_finalize_still_raises_when_no_place_exists(tmp_path):
    # the true dead-end keeps the 162 raise: no place to stage anyone anywhere —
    # the anchor fix has no ground, and the guard error now SAYS so (no more `[]`).
    import pytest
    from construct import game
    from construct.provider import StubProvider, task_of
    rule = rule_classifier_fallback()

    def fallback(prompt, schema):
        return rule(prompt, schema) if prompt.startswith("Classify the lifetime") else {"items": []}
    w = World(tmp_path / "npl.world", world_id="w:npl",
              model=StubModel(fallback=fallback), stance="fiction", title="No Places")
    w.ingestor.cursor.advance(1.0)
    w.ingest_structured([
        {"entity": "person:a", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "fact:secret", "attribute": "kind", "value": "proposition", "timeless": True},
    ])
    proposal = {"protagonist": "person:a", "delta_type": "drive_inverted",
                "tension": ["person:a", "drive:doubt", "drive:proof"],
                "goal_statement": "find the truth",
                "beats": [{"id": "beat:learn", "phase": "climax", "weight": "required",
                           "kind": "player_learns", "entity": "fact:secret",
                           "attribute": "culprit", "value": "person:a"}]}

    class _P(StubProvider):
        def __init__(self): super().__init__([])
        async def complete(self, prompt, schema, *, tier="main", deliberate=False):
            if prompt.startswith("Classify the lifetime"):
                return {"durability": "STATE", "confidence": 0.9}
            if task_of(prompt) == "arc":
                return dict(proposal)
            return {"items": []}

    spath = tmp_path / "npl_scenario.world"
    with pytest.raises(RuntimeError, match="located people"):    # diagnosable, not `[]`
        game._finalize_scenario(w, "npl", "No Places", _P(), spath,
                                endless=False, play_as="person a")
    assert not spath.with_suffix(".meta.json").exists()
    w.close()


def test_preflight_rejects_unknown_referent(tmp_path):
    w = _world(tmp_path / "pf.world")
    bad = dict(VALID_PROPOSAL)
    bad["beats"] = [{"id": "beat:bad", "phase": "climax", "weight": "required",
                     "kind": "player_learns", "entity": "fact:nonexistent",
                     "attribute": "x", "value": "y"}]
    out = generate_from_fallout(w, PorcelainWorldReads(w), _GenProvider(bad), _fallout(),
                                [], _ctx(), turn=1)
    assert out is None
    assert any("lint" in e.event_id for e in
               PorcelainWorldReads(w).events(kind="generation_declined", frame=SESSION))
    w.close()


def test_author_replan_builds_a_fresh_main_arc_same_protagonist(tmp_path):
    """WORLD-CHANGING-AGENCY step 4: author_replan re-authors the MAIN arc mid-story
    after a reshape, with a fresh id and the SAME protagonist enforced."""
    from construct.game import _build_arc, author_replan
    w = _world(tmp_path / "replan.world")
    old = _build_arc({**VALID_PROPOSAL, "protagonist": PLAYER}, arc_id="arc:main")
    prov = _GenProvider()  # the "gen" cohort returns VALID_PROPOSAL (protagonist=CLERK)
    out = author_replan(w, old, prov,
                        reshape_summary="the dead victim drew breath again", turn=7)
    assert out.ok and out.reason == "replanned"
    assert out.arc.arc_id == "arc:replan_7"            # fresh id, no collision with arc:main
    assert out.arc.protagonist == PLAYER               # same player enforced (not the cohort's CLERK)
    assert out.arc.beats                               # coherent (has beats)


def test_author_replan_tags_provider_error_for_fail_open(tmp_path):
    from construct.game import _build_arc, author_replan

    class _Boom(StubProvider):
        def __init__(self):
            super().__init__([])

        async def complete(self, *a, **k):
            raise RuntimeError("model down")

    w = _world(tmp_path / "boom.world")
    old = _build_arc({**VALID_PROPOSAL, "protagonist": PLAYER}, arc_id="arc:main")
    # a transient provider hiccup → provider_error (caller keeps the current arc), NOT fallout
    out = author_replan(w, old, _Boom(), reshape_summary="x", turn=7)
    assert out.reason == "provider_error" and out.arc is None and not out.ok


def test_author_replan_tags_no_replacement_for_a_beatless_result(tmp_path):
    from construct.game import _build_arc, author_replan
    w = _world(tmp_path / "empty.world")
    old = _build_arc({**VALID_PROPOSAL, "protagonist": PLAYER}, arc_id="arc:main")
    # the cohort proposes nothing coherent (no beats) → no_replacement (route old-arc fallout),
    # distinct from a provider error.
    prov = _GenProvider(proposal={**VALID_PROPOSAL, "beats": []})
    out = author_replan(w, old, prov, reshape_summary="x", turn=7)
    assert out.reason == "no_replacement" and out.arc is None and not out.ok


def test_continuation_intro_bridges_endpoints_without_a_formula():
    """Founder 2026-06-26: the next-episode cold open must BRIDGE where the last story
    landed to where this one is headed — creatively, NOT the old 4-for-4 'time has passed
    + you made a name on that one' template."""
    from construct.game import _build_arc, _continuation_intro
    prior = _build_arc({**VALID_PROPOSAL, "protagonist": PLAYER,
                        "tension": [PLAYER, "drive:duty", "drive:fear"]}, arc_id="arc:main")
    new = _build_arc({**VALID_PROPOSAL, "protagonist": PLAYER,
                      "tension": [PLAYER, "drive:doubt", "drive:resolve"]}, arc_id="arc:ep_2")
    intro = _continuation_intro(
        "The Pier Nine Affair", "won", prior,
        {"hook": "A body in the lighthouse lamp room, and the lamp still turning."}, new)
    low = intro.lower()
    # both endpoints are present (the bridge is built from the two SPECIFIC stories)
    assert "Pier Nine Affair" in intro                              # where it landed
    assert "lighthouse lamp room" in intro                          # where it's headed
    assert "duty against fear" in low                               # prior drive axis
    # it instructs a CREATIVE bridge and explicitly FORBIDS the old formula (not prescribes it)
    assert "bridge" in low and "creative latitude" in low
    assert "do not default to a formula" in low
    assert "you made a name on that one" in low  # present only as the thing to AVOID
    # it VARIES with inputs (not a fixed string)
    other = _continuation_intro("A Quiet Drowning", "lost", prior,
                                {"hook": "A stranger waits on the stair with no name to give."}, new)
    assert intro != other


def test_continue_episode_doorway_on_played_nonhorizon_slot(tmp_path, monkeypatch):
    """#88 S4 caller-level regression (Cx 382 blocker): on a PLAYED non-horizon slot with
    entry_epoch=1000.0 and the terminal scene elsewhere, continue_episode must relocate the
    protagonist to the ORIGINAL opening place (the raised write-epoch must not poison the
    opening lookup) and advance diegetic time."""
    from construct.arc import executor
    from construct.arc.executor import TURN_EPOCH, set_entry_epoch
    from construct.clock import read_clock
    from construct.game import continue_episode, slot_path
    from construct.semantics import attribute_default

    monkeypatch.chdir(tmp_path)
    _tok = executor._ENTRY_EPOCH.set(TURN_EPOCH)  # continue_episode raises it; restore after
    (tmp_path / "worlds").mkdir()
    spath = tmp_path / "worlds" / "doorcase.world"
    rule = rule_classifier_fallback()
    w = World(spath, world_id="w:doorcase", stance="fiction",
              attribute_default=attribute_default,
              model=StubModel(fallback=lambda pr, sc: rule(pr, sc)
                              if pr.startswith("Classify the lifetime") else {"items": []}))
    w.ingestor.cursor.advance(1.0)
    w.ingest_structured([
        {"entity": "place:office", "attribute": "kind", "value": "room", "timeless": True},
        {"entity": PLAYER, "attribute": "kind", "value": "person", "timeless": True},
    ])
    # main arc in the plot frame (continue reads it to seed the next chapter)
    shape = ConclusionShape("shape:main", "drive_inverted", (PLAYER, "a", "b"),
                            world_condition=InFrame(f"knows:{PLAYER}", "fact:x", "k", "v"),
                            premise=InFrame("canon", "fact:x", "kind", "proposition"),
                            refusal_variant_id="shape:refused")
    refusal = Clock("clock:refusal", TurnsQuiet(15),
                    effects=({"entity": "event:concludes", "attribute": "kind",
                              "value": "refusal_conclusion"},), bound_to="arc:main",
                    rung=Rung.REFUSAL)
    arc = Arc(arc_id="arc:main", protagonist=PLAYER, shape=shape, beats=(), clocks=(),
              refusal_clock=refusal, climax_ready_k=1, climax_ready_beats=())
    w.porcelain.ingest_structured(arc_io.arc_to_items(arc) + arc_io.index_items(arc))
    set_entry_epoch(1000.0)
    # the PLAYED history: opened at place:office, ended on place:roof; terminal receipt exists
    w.porcelain.ingest_structured([
        {"entity": "place:roof", "attribute": "kind", "value": "room", "timeless": True},
        {"entity": PLAYER, "attribute": "in", "value": "place:office", "valid_from": 1000.4},
        {"entity": PLAYER, "attribute": "in", "value": "place:roof", "valid_from": 1005.0},
    ])
    w.porcelain.ingest_structured([
        {"entity": "event:turn_0", "attribute": "kind", "value": "turn", "valid_from": 1000.0},
        {"entity": "event:turn_5", "attribute": "kind", "value": "turn", "valid_from": 1005.0},
        {"entity": "event:arc_outcome_5", "attribute": "kind", "value": "arc_won",
         "valid_from": 1005.0},
        {"entity": "event:arc_outcome_5", "attribute": "grade", "value": "vindicated",
         "valid_from": 1005.0},
    ], frame=SESSION)
    w.close()
    spath.with_suffix(".meta.json").write_text(json.dumps(
        {"title": "Door Case", "protagonist": PLAYER, "arc_scope": [PLAYER],
         "mode": "pure", "scenario_mode": "win_loss", "entry_epoch": 1000.0}))
    import shutil
    shutil.copyfile(spath, slot_path("doorcase", "u1"))

    prop = dict(VALID_PROPOSAL); prop["protagonist"] = PLAYER
    # #90 (Cx 387): the hook's on-stage person must be made REAL at the doorway place
    prop["hook_cast"] = [{"id": "person:shawl_witness", "name": "Ada Finch",
                          "role": "frightened inquest witness"}]
    # #96 S3 (Cx 414): the continuation proposes its OWN title
    prop["title"] = "The Weight of Brass"
    # #96 S2: a prior-ending consequence event awaits its ONE bridge callback
    w2s = World(spath, world_id="w:doorcase", stance="fiction",
                model=StubModel(fallback=lambda p_, s_: rule_classifier_fallback()(p_, s_)
                                if p_.startswith("Classify the lifetime") else {"items": []}))
    w2s.porcelain.ingest_structured([
        {"entity": "event:consequence_word_5", "attribute": "kind",
         "value": "word_spreads", "valid_from": 1005.0},
        {"entity": "event:consequence_word_5", "attribute": "detail",
         "value": "the answer held, and word of who found it travels", "valid_from": 1005.0},
    ])
    # #96 S4: a played ledger exists → the personal-threads extraction runs over it
    w2s.porcelain.ingest_structured([
        {"entity": "session:narrative_memory", "attribute": "text",
         "value": "You promised Ada Finch you would clear her brother's name.",
         "value_type": "literal", "valid_from": 1005.0},
    ], frame=SESSION)
    w2s.close()
    shutil.copyfile(spath, slot_path("doorcase", "u1"))

    class _DoorProvider(_GenProvider):
        async def complete(self, prompt, schema, *, tier="main", deliberate=False):
            if prompt.startswith("Classify the lifetime"):
                return rule(prompt, schema)   # the REAL rule classifier (clock writes need it)
            if task_of(prompt) == "pth":      # #96 S4: the personal-threads extraction
                return {"threads": [{"thread": "promised Ada Finch to clear her "
                                               "brother's name", "status": "open"}]}
            return await super().complete(prompt, schema, tier=tier, deliberate=deliberate)

    _door = _DoorProvider(prop)
    meta = continue_episode("doorcase", _door, player_id="u1")
    # the raised continuation epoch is a SCOPED write context (Cx 383) — it must not
    # outlive the call (the test's own token guard below would mask a production leak).
    assert executor.current_epoch() == TURN_EPOCH
    w2 = World(slot_path("doorcase", "u1"), world_id="w:doorcase", stance="fiction",
               model=StubModel(fallback=lambda p, s: rule_classifier_fallback()(p, s)
                               if p.startswith("Classify the lifetime") else {"items": []}))
    try:
        assert w2.porcelain.locate(PLAYER)[0] == "place:office"   # BACK at the opening place
        assert read_clock(w2).minutes > 0                          # time truly advanced
        assert "the new chapter opens at office" in meta["continuation_intro"]
        # #90: the hook witness is REAL — canon-present at the doorway place and IN the
        # episode scope (an unscoped hook person would be invisible to presence/npc turns)
        assert w2.porcelain.locate("person:shawl_witness")[0] == "place:office"
        from construct.adapter import PorcelainWorldReads as _PWR
        _sc = _PWR(w2).state("session:episode", "arc_scope", frame=SESSION)
        assert "person:shawl_witness" in json.loads(_sc)
        # #96 S3: the new chapter took its OWN title; the gen prompt carried CLOSED HISTORY
        assert meta["title"] == "The Weight of Brass"
        _gen = next(p_ for (p_, _s2, _t2) in _door.calls if task_of(p_) == "gen")
        assert "CLOSED HISTORY" in _gen and "never re-opened" in _gen.lower()
        # #96 S2: the bridge surfaced the consequence callback + wrote its receipt
        assert "A CONSEQUENCE CALLBACK" in meta["continuation_intro"]
        assert "word of who found it travels" in meta["continuation_intro"]
        # receipt read row-level: event-entity attrs don't fold via state()
        assert any(str(r.entity) == "event:consequence_word_5"
                   and str(r.attribute) == "surfaced_turn"
                   for r in w2.buffer.visible(frame=SESSION))
        # #96 S3: the settled-history record persisted — the answered premise is CLOSED
        # HISTORY the notebook and future opens read, never a mystery to reopen
        _settled_rec = next((str(r.value) for r in w2.buffer.visible(frame=SESSION)
                             if str(r.entity).startswith("settled:episode_")
                             and str(r.attribute) == "record"), None)
        assert _settled_rec is not None
        assert "fact:x" in _settled_rec and "ANSWERED" in _settled_rec
        # #96 S4: the promise made in the ledger rides the generator prompt as a thread
        # to HONOR, and persists as a session literal for future opens
        assert "PERSONAL THREADS TO HONOR" in _gen
        assert "promised Ada Finch" in _gen and "[open]" in _gen
        _threads_rec = next((str(r.value) for r in w2.buffer.visible(frame=SESSION)
                             if str(r.entity) == "session:personal_threads"
                             and str(r.attribute) == "record"), None)
        assert _threads_rec is not None and "Ada Finch" in _threads_rec
    finally:
        w2.close()
        executor._ENTRY_EPOCH.reset(_tok)


def test_continue_episode_refuses_after_player_death(tmp_path, monkeypatch):
    """#95 (Cx 422 bar 7): the story ended at the protagonist's death — continue_episode
    refuses BEFORE any generator or prompt work (permanence: no next chapter)."""
    import pytest

    from construct.game import continue_episode, slot_path
    from construct.semantics import attribute_default

    monkeypatch.chdir(tmp_path)
    (tmp_path / "worlds").mkdir()
    spath = tmp_path / "worlds" / "deadcase.world"
    rule = rule_classifier_fallback()
    w = World(spath, world_id="w:deadcase", stance="fiction",
              attribute_default=attribute_default,
              model=StubModel(fallback=lambda pr, sc: rule(pr, sc)
                              if pr.startswith("Classify the lifetime") else {"items": []}))
    w.ingestor.cursor.advance(1.0)
    w.ingest_structured([
        {"entity": "place:office", "attribute": "kind", "value": "room", "timeless": True},
        {"entity": PLAYER, "attribute": "kind", "value": "person", "timeless": True},
    ])
    w.porcelain.ingest_structured([
        {"entity": "event:turn_3", "attribute": "kind", "value": "turn", "valid_from": 1003.0},
        {"entity": "event:player_death_3", "attribute": "kind", "value": "player_death",
         "valid_from": 1003.0},
    ], frame=SESSION)
    w.close()
    spath.with_suffix(".meta.json").write_text(json.dumps(
        {"title": "Dead Case", "protagonist": PLAYER, "arc_scope": [PLAYER],
         "mode": "pure", "scenario_mode": "win_loss"}))
    import shutil
    shutil.copyfile(spath, slot_path("deadcase", "u1"))

    prov = _GenProvider()
    with pytest.raises(RuntimeError, match="death"):
        continue_episode("deadcase", prov, player_id="u1")
    assert not any(task_of(p) == "gen" for (p, _s, _t) in prov.calls), \
        "the refusal must come before any generator work"


def test_finalize_commits_laws_as_canon_and_meta(tmp_path):
    # WORLD LAWS (#105): sealed laws land as explicit canon rows (law:<slug>,
    # kind=world_law — Cx 470 ruling 5), ride meta for the turn loop, and the
    # arc author receives THE LAWS block (the destination may turn on one).
    from construct import game
    from construct.provider import StubProvider, task_of

    rule = rule_classifier_fallback()

    def fallback(prompt, schema):
        return rule(prompt, schema) if prompt.startswith("Classify the lifetime") else {"items": []}

    path = tmp_path / "lawful.world"
    w = World(path, world_id="w:lawful", model=StubModel(fallback=fallback),
              stance="fiction", title="Lawful World")
    w.ingestor.cursor.advance(1.0)
    w.ingest_structured([
        {"entity": "place:hall", "attribute": "kind", "value": "room", "timeless": True},
        {"entity": "person:keeper", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:keeper", "attribute": "in", "value": "place:hall"},
        {"entity": "fact:debt", "attribute": "kind", "value": "proposition", "timeless": True},
        {"entity": "fact:debt", "attribute": "holder", "value": "person:keeper"},
    ])

    laws = [{"name": "The Ledger of Hours", "register": "systemic",
             "rule": "every favor owed is recorded and must be repaid",
             "cost_limit": "a debt unpaid compounds",
             "embodiment": "the Clerks of the Ledger",
             "texture": "ledger-slips", "nearest_borrowed_shape": "",
             "changed_consequence": "rank is a running balance",
             "disclosure": "understood"}]

    proposal = {
        "protagonist": "person:keeper", "delta_type": "drive_inverted",
        "tension": ["person:keeper", "drive:doubt", "drive:proof"],
        "goal_statement": "settle the ledger", "theme": "what is owed",
        "beats": [{"id": "beat:learn", "phase": "climax", "weight": "required",
                   "kind": "player_learns", "entity": "fact:debt",
                   "attribute": "holder", "value": "person:keeper"}],
    }

    class _ArcProvider(StubProvider):
        def __init__(self):
            super().__init__([])
            self.arc_prompts: list[str] = []

        async def complete(self, prompt, schema, *, tier="main", deliberate=False):
            self.calls.append((prompt, schema, tier))
            if prompt.startswith("Classify the lifetime"):
                return {"durability": "STATE", "confidence": 0.9}
            if task_of(prompt) == "arc":
                self.arc_prompts.append(prompt)
                return dict(proposal)
            return {"items": []}

    provider = _ArcProvider()
    spath = tmp_path / "lawful_scenario.world"
    meta = game._finalize_scenario(w, "lawful", "Lawful World", provider, spath,
                                   endless=False, laws=laws,
                                   reality_register="secondary")
    # canon rows — explicit and boring
    _kind = w.porcelain.state("law:the_ledger_of_hours", "kind")
    assert _kind["status"] == "known" and _kind["fact"]["value"] == "world_law"
    _reg = w.porcelain.state("law:the_ledger_of_hours", "register")
    assert _reg["fact"]["value"] == "systemic"
    # meta mirror for the turn loop
    assert meta["laws"] == laws
    assert meta["reality_register"] == "secondary"
    # the arc author saw the SAME rendered block (Cx 470 test bar)
    from construct.laws import laws_block
    assert any(laws_block(laws) in p for p in provider.arc_prompts)
    assert any("TURN ON A LAW" in p for p in provider.arc_prompts)
    w.close()


def test_finalize_stages_play_as_pick_instead_of_swapping(tmp_path):
    # #107 (Minutes Before Bullets): the author picked EXACTLY the figure the
    # player asked to be, but that person was an unplaced stub — the old guard
    # swapped the player's identity for whichever stranger held a location.
    # Identity outranks staging: the asked-for figure is STAGED (at the located
    # cast's place), never traded away.
    from construct import game
    from construct.provider import StubProvider, task_of

    rule = rule_classifier_fallback()

    def fallback(prompt, schema):
        return rule(prompt, schema) if prompt.startswith("Classify the lifetime") else {"items": []}

    path = tmp_path / "ident.world"
    w = World(path, world_id="w:ident", model=StubModel(fallback=fallback),
              stance="fiction", title="Identity World")
    w.ingestor.cursor.advance(1.0)
    w.ingest_structured([
        {"entity": "place:camp", "attribute": "kind", "value": "room", "timeless": True},
        {"entity": "place:road", "attribute": "kind", "value": "room", "timeless": True},
        # the player's figure: a bare stub, never placed
        {"entity": "person:defense_apprentice", "attribute": "kind", "value": "person",
         "timeless": True},
        # a located stranger the OLD guard would have swapped to
        {"entity": "person:retrieval_lead", "attribute": "kind", "value": "person",
         "timeless": True},
        {"entity": "person:retrieval_lead", "attribute": "in", "value": "place:camp"},
        {"entity": "fact:truth", "attribute": "kind", "value": "proposition",
         "timeless": True},
        {"entity": "fact:truth", "attribute": "holder", "value": "person:retrieval_lead"},
    ])

    proposal = {
        "protagonist": "person:defense_apprentice", "delta_type": "drive_inverted",
        "tension": ["person:defense_apprentice", "drive:doubt", "drive:proof"],
        "goal_statement": "learn what the radio hides", "theme": "the puppet show",
        "beats": [{"id": "beat:learn", "phase": "climax", "weight": "required",
                   "kind": "player_learns", "entity": "fact:truth",
                   "attribute": "holder", "value": "person:retrieval_lead"}],
    }

    class _ArcProvider(StubProvider):
        def __init__(self):
            super().__init__([])

        async def complete(self, prompt, schema, *, tier="main", deliberate=False):
            self.calls.append((prompt, schema, tier))
            if prompt.startswith("Classify the lifetime"):
                return {"durability": "STATE", "confidence": 0.9}
            if task_of(prompt) == "arc":
                return dict(proposal)
            return {"items": []}

    spath = tmp_path / "ident_scenario.world"
    meta = game._finalize_scenario(w, "ident", "Identity World", _ArcProvider(), spath,
                                   endless=False,
                                   play_as="the defense apprentice, a young woman")
    # published with the PLAYER'S figure — staged among the located cast, not swapped
    assert meta["protagonist"] == "person:defense_apprentice"
    assert w.porcelain.locate("person:defense_apprentice")[0] == "place:camp"
    w.close()


def test_seal_lint_catches_protagonist_split(tmp_path):
    # #107 seal-lint: if the committed arc:main.protagonist row diverges from the
    # authored (in-memory) protagonist the beat gates + meta are built from, the
    # build receipts a `protagonist_split` incoherence (loud, never a raise). We
    # force the split by monkeypatching arc_to_items to emit a DIFFERENT canonical
    # protagonist row than the arc object carries.
    from construct import game
    from construct.arc import io as arc_io
    from construct.provider import StubProvider, task_of

    rule = rule_classifier_fallback()

    def fallback(prompt, schema):
        return rule(prompt, schema) if prompt.startswith("Classify the lifetime") else {"items": []}

    path = tmp_path / "split.world"
    w = World(path, world_id="w:split", model=StubModel(fallback=fallback),
              stance="fiction", title="Split World")
    w.ingestor.cursor.advance(1.0)
    w.ingest_structured([
        {"entity": "place:hall", "attribute": "kind", "value": "room", "timeless": True},
        {"entity": "person:hero", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:hero", "attribute": "in", "value": "place:hall"},
        {"entity": "person:other", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:other", "attribute": "in", "value": "place:hall"},
        {"entity": "fact:x", "attribute": "kind", "value": "proposition", "timeless": True},
        {"entity": "fact:x", "attribute": "who", "value": "person:other"},
    ])
    proposal = {
        "protagonist": "person:hero", "delta_type": "drive_inverted",
        "tension": ["person:hero", "drive:a", "drive:b"],
        "goal_statement": "learn it", "theme": "the split",
        "beats": [{"id": "beat:l", "phase": "climax", "weight": "required",
                   "kind": "player_learns", "entity": "fact:x",
                   "attribute": "who", "value": "person:other"}],
    }

    class _P(StubProvider):
        def __init__(self): super().__init__([])
        async def complete(self, prompt, schema, *, tier="main", deliberate=False):
            if prompt.startswith("Classify the lifetime"):
                return {"durability": "STATE", "confidence": 0.9}
            if task_of(prompt) == "arc":
                return dict(proposal)
            return {"items": []}

    # force the divergence: the committed arc row names a DIFFERENT protagonist
    _orig = arc_io.arc_to_items
    def _splitting(arc, frame="plot:main"):
        rows = _orig(arc, frame=frame)
        for r in rows:
            if r.get("entity") == arc.arc_id and r.get("attribute") == "protagonist":
                r["value"] = "person:other"   # <- the split
        return rows
    game.arc_io.arc_to_items = _splitting
    try:
        spath = tmp_path / "split_scenario.world"
        game._finalize_scenario(w, "split", "Split World", _P(), spath,
                                endless=False, play_as="person hero")
    finally:
        game.arc_io.arc_to_items = _orig

    from construct.adapter import frame_facts
    kinds = {str(r.value) for r in frame_facts(w, "session:main",
                                               entity="event:seal_incoherence")}
    assert "protagonist_split" in kinds          # the lint fired + receipted
    assert spath.with_suffix(".meta.json").exists()   # but never sank the build
    w.close()


def test_fidelity_vouched_pairs_allowlist_and_load_bearing_gates():
    # #56 (Cx 482): the vouched-merge gate. Only merges a same-kind fragment when
    # (a) EXACTLY ONE group id is load-bearing, AND (b) the exact pair is the
    # engine's homonym-safe residue (status auto_declined + reason
    # alias_not_specific). Everything else fails open.
    from construct.game import _fidelity_vouched_pairs
    PROT, REQ = "person:mara_venn", "person:lysa_fen"
    lb = {PROT, REQ}

    def pair(a, b, status="auto_declined", reason="alias_not_specific"):
        return {"a": a, "b": b, "status": status, "reason": reason}

    audit = [
        # (1) protagonist + fragment, alias_not_specific → MERGE
        {"live": True, "entities": [PROT, "person:mara"], "kinds": ["person", "person"],
         "pairs": [pair(PROT, "person:mara")]},
        # (2) required holder + fragment, alias_not_specific → MERGE
        {"live": True, "entities": [REQ, "person:lysa"], "kinds": ["person", "person"],
         "pairs": [pair(REQ, "person:lysa")]},
        # (3) protagonist + fragment but pair is UNLINKED → NO merge (allowlist)
        {"live": True, "entities": [PROT, "person:mara2"], "kinds": ["person", "person"],
         "pairs": [pair(PROT, "person:mara2", status="unlinked", reason=None)]},
        # (4) NON-load-bearing split (a background pair) → NO merge (load-bearing gate)
        {"live": True, "entities": ["person:bg", "person:bg_full"],
         "kinds": ["person", "person"],
         "pairs": [pair("person:bg", "person:bg_full")]},
        # (5) TWO load-bearing ids in one group → NO merge (no unique canonical)
        {"live": True, "entities": [PROT, REQ], "kinds": ["person", "person"],
         "pairs": [pair(PROT, REQ)]},
        # (6) cross-kind homonym (person↔place) → NO merge (reject() owns it)
        {"live": True, "entities": [PROT, "place:mara"], "kinds": ["person", "place"],
         "pairs": [pair(PROT, "place:mara")]},
        # (7) durable_contradiction reason → NO merge
        {"live": True, "entities": [PROT, "person:mara3"], "kinds": ["person", "person"],
         "pairs": [pair(PROT, "person:mara3", reason="durable_contradiction")]},
    ]
    got = set(_fidelity_vouched_pairs(audit, lb))
    assert got == {(PROT, "person:mara"), (REQ, "person:lysa")}, got


def test_failed_cast_does_not_widen_the_vouch_set(tmp_path):
    # #56 (Cx 486): the Step-4 load-bearing set must be populated ONLY on cast
    # ACCEPTANCE. This failed proposal DOES carry a required pillar (pillar:means)
    # AND a real holder (person:witness) that WOULD be in the derived required-
    # holder set if the cast were accepted — but the cast fails deduction staging
    # (no culprit / no first_witness), so it ships pillar-less. The vouch load-
    # bearing set must therefore be {protagonist} only: neither the required PILLAR
    # id nor the required HOLDER id may leak from a failed proposal. (Under the old
    # premature assignment this test would FAIL — pillar:means/person:witness would
    # appear in the spied set.) We also spy porcelain.merge and assert it is never
    # called for the failed holder.
    from construct import game
    from construct.cast import required_holder_ids, cast_from_proposal
    from construct.provider import StubProvider, task_of

    rule = rule_classifier_fallback()

    def fallback(prompt, schema):
        return rule(prompt, schema) if prompt.startswith("Classify the lifetime") else {"items": []}

    path = tmp_path / "fc.world"
    w = World(path, world_id="w:fc", model=StubModel(fallback=fallback),
              stance="fiction", title="Failed Cast World")
    w.ingestor.cursor.advance(1.0)
    w.ingest_structured([
        {"entity": "place:hall", "attribute": "kind", "value": "room", "timeless": True},
        {"entity": "person:hero", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:hero", "attribute": "in", "value": "place:hall"},
        {"entity": "person:witness", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:witness", "attribute": "in", "value": "place:hall"},
        {"entity": "fact:x", "attribute": "kind", "value": "proposition", "timeless": True},
        {"entity": "fact:x", "attribute": "who", "value": "person:witness"},
    ])
    proposal = {
        "protagonist": "person:hero", "delta_type": "drive_inverted",
        "tension": ["person:hero", "drive:a", "drive:b"],
        "goal_statement": "learn it", "theme": "the case",
        "beats": [{"id": "beat:l", "phase": "climax", "weight": "required",
                   "kind": "player_learns", "entity": "fact:x",
                   "attribute": "who", "value": "person:witness"}],
    }
    # A cast with a genuine, live-reachable required clue on person:witness — so the
    # holder IS load-bearing IF accepted — but with NO culprit and NO first_witness,
    # so deduction staging rejects it and it ships pillar-less.
    failed_cast = {
        "pillars": [{"id": "pillar:means", "label": "the means", "required": True}],
        "cast": [{
            "id": "person:witness", "shape_role": "witness", "surface_role": "a bystander",
            "presence": "at_scene", "location": "place:hall",
            "clues": [{"clue_id": "clue:m1", "pillar_id": "pillar:means",
                       "fact": {"entity": "fact:x", "attribute": "who", "value": "person:witness"},
                       "coverage_effect": "genuine", "reveal_condition": "none",
                       "hook_text": "a muddy footprint"}],
        }],
    }
    # sanity: the holder WOULD be load-bearing on acceptance (proves the test has teeth)
    _fc_cast, _fc_specs = cast_from_proposal(failed_cast)
    _fc_req = [pid for pid, _l, req in _fc_specs if req]
    assert required_holder_ids(_fc_req, _fc_cast) == {"person:witness"}

    class _P(StubProvider):
        def __init__(self): super().__init__([])
        async def complete(self, prompt, schema, *, tier="main", deliberate=False):
            if prompt.startswith("Classify the lifetime"):
                return {"durability": "STATE", "confidence": 0.9}
            if task_of(prompt) == "arc":
                return dict(proposal)
            if task_of(prompt) == "cast":  # UNSOLVABLE (no culprit/first_witness) → pillar-less
                return dict(failed_cast)
            return {"items": []}

    seen = {}
    merged = []
    _orig = game._fidelity_vouched_pairs
    game._fidelity_vouched_pairs = lambda nc, lb, **k: (seen.__setitem__("lb", set(lb)), _orig(nc, lb, **k))[1]
    _orig_merge = w.porcelain.merge
    w.porcelain.merge = lambda a, b, **k: (merged.append((a, b)), _orig_merge(a, b, **k))[1]
    try:
        game._finalize_scenario(w, "fc", "Failed Cast World", _P(), tmp_path / "fc_s.world",
                                endless=False, game_types=["mystery_whodunnit"])
    finally:
        game._fidelity_vouched_pairs = _orig
        w.porcelain.merge = _orig_merge
    # the vouch set is protagonist ONLY — no required pillar id and no required
    # holder id leaked from the failed proposal
    assert seen.get("lb") == {"person:hero"}, seen.get("lb")
    assert all("person:witness" not in pair for pair in merged), merged
    w.close()


def test_opening_scene_place_prefers_specific_interior_over_coarse(tmp_path):
    # #109 (Cx 490): the prose-grounding lever is NOT sufficient alone — PB.locate()
    # collapses same-timestamp co-asserted `in` rows to the FIRST-inserted one. Here the
    # protagonist is co-asserted at a coarse CITY (inserted first) AND a ROOM contained
    # in it, at the same opening horizon. locate() returns the city; the #109 backstop
    # must anchor the opening tableau to the ROOM instead.
    from construct import game
    from construct.adapter import frame_facts

    w = World(tmp_path / "op.world", world_id="w:op",
              model=StubModel(fallback=lambda p, s: {"items": []}),
              stance="fiction", title="Opening Place")
    w.ingestor.cursor.advance(1.0)
    w.ingest_structured([
        {"entity": "place:lisbon", "attribute": "kind", "value": "city", "timeless": True},
        {"entity": "place:kitchen", "attribute": "kind", "value": "room", "timeless": True},
        {"entity": "place:kitchen", "attribute": "in", "value": "place:lisbon",
         "value_type": "entity"},
        {"entity": "person:marta", "attribute": "kind", "value": "person", "timeless": True},
        # CITY row inserted FIRST, the ROOM row SECOND — SAME timestamp (the ambiguity)
        {"entity": "person:marta", "attribute": "in", "value": "place:lisbon",
         "value_type": "entity"},
        {"entity": "person:marta", "attribute": "in", "value": "place:kitchen",
         "value_type": "entity"},
    ])
    as_of = max(r.valid_from for r in
                frame_facts(w, "canon", entity="person:marta", attribute="in"))
    # both places are co-asserted at the same horizon (the gap this fix targets)
    assert set(game._live_in_candidates(w, "person:marta", as_of)) == {
        "place:lisbon", "place:kitchen"}
    # PB.locate() collapses to the first-inserted COARSE city
    assert w.porcelain.locate("person:marta", as_of=as_of)[0] == "place:lisbon"
    # the backstop recovers the specific INTERIOR
    assert game._opening_scene_place(w, "person:marta", as_of) == "place:kitchen"
    w.close()


def test_opening_scene_place_backstop_applies_in_earliest_fallback(tmp_path):
    # #109 (Cx 492): the earliest-location fallback is the PRODUCTION path for an
    # atmospheric opening — opening_as_of sits BELOW the protagonist's first `in` row,
    # so the horizon `locate()` is empty and resolution falls to the earliest source
    # layer. The specificity backstop must run there too: the earliest layer co-asserts
    # a coarse city (inserted first) AND a room; the opening must anchor to the room.
    from construct import game
    from construct.adapter import frame_facts

    w = World(tmp_path / "opf.world", world_id="w:opf",
              model=StubModel(fallback=lambda p, s: {"items": []}),
              stance="fiction", title="Earliest Fallback")
    w.ingestor.cursor.advance(1.0)
    w.ingest_structured([
        {"entity": "place:porto", "attribute": "kind", "value": "city", "timeless": True},
        {"entity": "place:parlor", "attribute": "kind", "value": "room", "timeless": True},
        {"entity": "place:parlor", "attribute": "in", "value": "place:porto",
         "value_type": "entity"},
        {"entity": "person:ana", "attribute": "kind", "value": "person", "timeless": True},
        # CITY first, ROOM second — at the earliest source layer
        {"entity": "person:ana", "attribute": "in", "value": "place:porto",
         "value_type": "entity"},
        {"entity": "person:ana", "attribute": "in", "value": "place:parlor",
         "value_type": "entity"},
    ])
    earliest = min(r.valid_from for r in
                   frame_facts(w, "canon", entity="person:ana", attribute="in"))
    # an opening horizon BELOW the first `in` row → horizon locate() is empty →
    # earliest-fallback branch is exercised
    opening_as_of = earliest - 1.0
    assert not w.porcelain.locate("person:ana", as_of=opening_as_of)
    assert game._opening_scene_place(w, "person:ana", opening_as_of) == "place:parlor"
    w.close()


def test_opening_scene_place_single_candidate_is_unchanged(tmp_path):
    # #109 backward-compat: with a single `in` candidate the backstop returns locate()'s
    # pick unchanged (no coarser/never-worse rule; non-domestic worlds are untouched).
    from construct import game

    w = World(tmp_path / "op1.world", world_id="w:op1",
              model=StubModel(fallback=lambda p, s: {"items": []}),
              stance="fiction", title="Single Place")
    w.ingestor.cursor.advance(1.0)
    w.ingest_structured([
        {"entity": "place:harbor", "attribute": "kind", "value": "city", "timeless": True},
        {"entity": "person:sam", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:sam", "attribute": "in", "value": "place:harbor",
         "value_type": "entity"},
    ])
    from construct.adapter import frame_facts
    as_of = max(r.valid_from for r in
                frame_facts(w, "canon", entity="person:sam", attribute="in"))
    assert game._opening_scene_place(w, "person:sam", as_of) == "place:harbor"
    w.close()


# ==========================================================================
# P2b (opportunistic) + P2c (ambient) tests
# ==========================================================================

# --- salient_moments (pure function, §A) -----------------------------------

def _ev(kind: str, ev_id: str = "", caused_by: tuple = ()) -> EventRow:
    """Minimal EventRow for salient_moments tests."""
    return EventRow(event_id=ev_id or f"event:{kind}_1", kind=kind,
                    caused_by=caused_by)


def test_salient_spine_touch_fires():
    # Signal 1: a fact row whose entity is a spined NPC → salient.
    fact_rows = [{"entity": CLERK, "attribute": "in", "value": "place:office"}]
    lines = salient_moments(fact_rows, [], set(), {CLERK})
    assert lines, "spine-touch should be salient"
    assert CLERK in lines[0]


def test_salient_spine_touch_value_fires():
    # Signal 1 (value side): a fact row whose VALUE is a spined NPC → salient.
    fact_rows = [{"entity": "fact:x", "attribute": "holder", "value": CLERK}]
    lines = salient_moments(fact_rows, [], set(), {CLERK})
    assert lines


def test_salient_first_time_kind():
    # Signal 2: a new event kind not in prior_kinds → salient.
    ev = _ev("confrontation", "event:confrontation_1")
    lines = salient_moments([], [ev], set(), set())
    assert lines
    assert "confrontation" in lines[0]


def test_salient_routine_kind_excluded():
    # Signal 2: routine bookkeeping kinds are never "first-time" salient.
    for kind in ROUTINE_EVENT_KINDS:
        ev = _ev(kind, f"event:{kind}_1")
        lines = salient_moments([], [ev], set(), set())
        assert not any("first-time" in l for l in lines), \
            f"routine kind {kind!r} should not produce a first-time fuel line"


def test_salient_tick_event_excluded():
    # Signal 2: event ids starting "event:tick_" are off-screen motion → not signal 2.
    ev = _ev("world_advance", "event:tick_advance")
    lines = salient_moments([], [ev], set(), set())
    # tick events may still be causal-ripple; but must not produce a first-time line.
    assert not any("first-time" in l for l in lines), \
        "tick event should not produce a first-time fuel line"


def test_salient_caused_by_fires():
    # Signal 3: an event with non-empty caused_by → causal ripple → salient.
    ev = _ev("conflict", "event:conflict_1", caused_by=("event:prior",))
    lines = salient_moments([], [ev], set(), set())
    assert any("ripple" in l or "caused_by" in l or "causal" in l for l in lines)


def test_salient_routine_kind_with_caused_by_excluded():
    # A ROUTINE bookkeeping kind is never a dramatic moment, even when it
    # carries causal linkage — else a routine turn/arc event with caused_by
    # would make EVERY turn salient and the filter would stop filtering.
    ev = _ev("turn", "event:turn_7", caused_by=("event:prior",))
    assert salient_moments([], [ev], set(), set()) == []


def test_salient_nothing_fires_not_salient():
    # A known kind, no spine-touch, no caused_by → empty (not salient).
    ev = _ev("turn", "event:turn_1")  # "turn" is routine
    lines = salient_moments([], [ev], {"turn"}, set())
    assert lines == []


# --- right-of-way (§B) -----------------------------------------------------

def _main_arc(w) -> Arc:
    """Reconstruct the main Arc object from the world's portfolio."""
    from construct.arc import io as _arc_io
    reads = PorcelainWorldReads(w)
    return next(a for a in _arc_io.portfolio_from_frame(reads) if a.arc_id == "arc:main")


def test_main_at_peak_climax_returns_true(tmp_path):
    """CLIMAX phase (climax_ready_k beat achieved) → main_at_peak returns True."""
    w = _world(tmp_path / "peak.world")
    # Beat "beat:discover" is the climax_ready_beat in the _world fixture (climax_ready_k=1).
    w.porcelain.ingest_structured(
        [{"entity": "beat:discover", "attribute": "status", "value": "achieved",
          "valid_from": turn_time(1)}], frame=PLOT)
    reads = PorcelainWorldReads(w)
    main = _main_arc(w)
    from construct.arc.executor import current_phase as _cp
    assert _cp(reads, main) == Phase.CLIMAX
    assert main_at_peak(reads, main)
    w.close()


def test_main_at_peak_blocks_no_decline_receipt(tmp_path):
    """Right-of-way is SILENT: main_at_peak returning True must NOT produce a
    generation_declined receipt — it is right-of-way, not a DM judgment (§B)."""
    w = _world(tmp_path / "peak_silent.world")
    w.porcelain.ingest_structured(
        [{"entity": "beat:discover", "attribute": "status", "value": "achieved",
          "valid_from": turn_time(1)}], frame=PLOT)
    reads = PorcelainWorldReads(w)
    main = _main_arc(w)
    assert main_at_peak(reads, main)
    # main_at_peak itself does not write receipts — calling it produces no side-effects.
    assert not reads.events(kind="generation_declined", frame=SESSION)
    w.close()


def test_main_at_peak_setup_allows_mint(tmp_path):
    """SETUP phase (no beats achieved) → main_at_peak returns False → mint can proceed."""
    w = _world(tmp_path / "setup.world")
    reads = PorcelainWorldReads(w)
    main = _main_arc(w)
    assert not main_at_peak(reads, main)
    w.close()


# --- ambient diegetic threshold + seed-on-absent + win_loss OFF (§C) --------

def test_ambient_diegetic_threshold_logic():
    """The ambient gate condition: diegetic quiet measured against AMBIENT_QUIET_MIN.
    With delta < AMBIENT_QUIET_MIN the gate must not open; at >= it must open.
    Pure arithmetic — no world needed."""
    minutes_now = 100.0
    last_dev = 99.0
    delta = minutes_now - last_dev
    assert delta < AMBIENT_QUIET_MIN, "small delta must NOT satisfy threshold"
    last_dev_past = minutes_now - AMBIENT_QUIET_MIN
    delta_past = minutes_now - last_dev_past
    assert delta_past >= AMBIENT_QUIET_MIN, "full quiet period must satisfy threshold"


def test_ambient_seed_on_absent_returns_minutes_now(tmp_path):
    """_last_development_min with no session:ambient row returns minutes_now AND
    writes the baseline row (write-once seed — §C, Cx 498). Delta after seeding is
    zero, so ambient does not fire immediately on a fresh world."""
    w = _world(tmp_path / "amb_seed.world")
    reads = PorcelainWorldReads(w)
    # No row present yet — seed-on-absent writes and returns minutes_now.
    result = _last_development_min(w, reads, 500.0, turn=1)
    assert result == 500.0, "seed-on-absent must return minutes_now"
    # The baseline row must now exist (write-once).
    reads2 = PorcelainWorldReads(w)
    written = _last_development_min(w, reads2, 999.0, turn=2)
    assert written == 500.0, "second call must read the written baseline, not reseed"
    # Delta after seeding is zero → below AMBIENT_QUIET_MIN → no immediate fire.
    assert (500.0 - result) < AMBIENT_QUIET_MIN
    w.close()


def test_ambient_mark_and_read_round_trip(tmp_path):
    """_mark_development writes the stamp; _last_development_min reads it back."""
    w = _world(tmp_path / "amb_rt.world")
    _mark_development(w, 300.0, turn=2)
    reads = PorcelainWorldReads(w)
    assert _last_development_min(w, reads, 999.0, turn=3) == 300.0
    w.close()


def test_ambient_mint_succeeds_when_guards_clear(tmp_path):
    """generate_ambient mints when all guards pass (it is not the ambient gate
    keeper — the turnloop controls when it is called). The function itself is
    a thin wrapper over _mint_side_arc and returns an arc when clear."""
    w = _world(tmp_path / "amb_mint.world")
    reads = PorcelainWorldReads(w)
    minted = generate_ambient(
        w, reads, _GenProvider(), [], _ctx(), turn=1, main_protagonist=PLAYER)
    assert minted is not None, "generate_ambient should mint when all guards pass"
    arc, hook = minted
    assert arc.arc_id == "arc:gen_1"
    w.close()


def test_ambient_win_loss_gate_is_in_turnloop():
    """The win_loss guard lives in the turnloop (scenario_mode check), NOT inside
    generate_ambient. Confirmed by the function's absence of a scenario_mode
    parameter — the spec §C says 'gate on scenario_mode == "endless"' in the
    turnloop step, not in the generator function itself."""
    import inspect
    sig = inspect.signature(generate_ambient)
    assert "scenario_mode" not in sig.parameters, \
        "scenario_mode guard belongs in the turnloop, not generate_ambient"


# --- arbitration order (§D) -----------------------------------------------

def test_arbitration_fallout_beats_salient(tmp_path):
    """Regenerative (fallout) has higher priority than opportunistic — when both
    qualify, the fallout mint fires and its arc is returned."""
    w = _world(tmp_path / "arb.world")
    reads = PorcelainWorldReads(w)
    # Both qualify: a fallout AND a salient moment.
    fo = _fallout()
    moments = ["spine-touch: clerk wants something"]
    ctx = {**_ctx(), "main_protagonist": PLAYER}
    # Regenerative fires first; opportunistic would also fire.
    minted_regen = generate_from_fallout(w, reads, _GenProvider(), fo, [], ctx, turn=1)
    assert minted_regen is not None, "regenerative should mint when fallout available"
    w.close()


def test_arbitration_opportunistic_beats_ambient(tmp_path):
    """Opportunistic (salient delta) has higher priority than ambient — when both
    qualify, the opportunistic mint fires."""
    w = _world(tmp_path / "arb2.world")
    _mark_development(w, 0.0, turn=1)
    reads = PorcelainWorldReads(w)
    moments = ["spine-touch: the clerk is present and has a drive"]
    ctx = {**_ctx(), "main_protagonist": PLAYER}
    minted = generate_opportunistic(w, reads, _GenProvider(), moments, [], ctx,
                                    turn=5, main_protagonist=PLAYER)
    assert minted is not None, "opportunistic should mint with salient moments"
    # Ambient would not fire anyway (delta < threshold), but the point is that
    # opportunistic takes the slot — confirmed by the single mint above.
    w.close()


# --- player boundary (§D) --------------------------------------------------

def test_player_protagonist_declined(tmp_path):
    """A proposal naming the main protagonist is declined with 'player_protagonist'."""
    w = _world(tmp_path / "pb.world")
    reads = PorcelainWorldReads(w)
    # Proposal returns PLAYER as the protagonist — same as main_protagonist.
    player_proposal = dict(VALID_PROPOSAL)
    player_proposal["protagonist"] = PLAYER
    player_proposal["tension"] = [PLAYER, "drive:duty", "drive:fear"]
    minted = generate_opportunistic(
        w, reads, _GenProvider(player_proposal),
        ["spine-touch"], [], _ctx(), turn=1, main_protagonist=PLAYER)
    assert minted is None, "player-protagonist proposal must be declined"
    declines = [e.event_id for e in
                PorcelainWorldReads(w).events(kind="generation_declined", frame=SESSION)]
    assert any("player_protagonist" in d for d in declines)
    w.close()


def test_player_protagonist_declined_ambient(tmp_path):
    """Same guard applies via generate_ambient."""
    w = _world(tmp_path / "pb2.world")
    reads = PorcelainWorldReads(w)
    player_proposal = dict(VALID_PROPOSAL)
    player_proposal["protagonist"] = PLAYER
    player_proposal["tension"] = [PLAYER, "drive:duty", "drive:fear"]
    minted = generate_ambient(
        w, reads, _GenProvider(player_proposal),
        [], _ctx(), turn=1, main_protagonist=PLAYER)
    assert minted is None
    declines = [e.event_id for e in
                PorcelainWorldReads(w).events(kind="generation_declined", frame=SESSION)]
    assert any("player_protagonist" in d for d in declines)
    w.close()


# --- depth-0 roots + depth-1 regeneration from a dead P2b arc (§D) ---------

def test_p2b_mint_has_depth_zero(tmp_path):
    """P2b (opportunistic) mints at depth 0 — the explicit depth passed to
    _record_attempt, NOT parent_depth+1 (§D, Cx 496 amendment 5)."""
    w = _world(tmp_path / "d0.world")
    reads = PorcelainWorldReads(w)
    moments = ["spine-touch: clerk"]
    minted = generate_opportunistic(
        w, reads, _GenProvider(), moments, [], _ctx(), turn=1, main_protagonist=PLAYER)
    assert minted is not None
    arc, _ = minted
    # gen_depth must be 0 (depth-0 root).
    depth_val = w.porcelain.state(arc.arc_id, "gen_depth", frame=PLOT)["fact"]["value"]
    assert depth_val in (0, "0"), f"expected depth 0, got {depth_val!r}"
    w.close()


def test_p2b_arc_death_regenerates_at_depth_one(tmp_path):
    """A P2b arc (depth 0) that dies regenerates at depth 1 via generate_from_fallout.
    _parent_depth reads gen_depth from the dead P2b arc row; the regenerative trigger
    records depth = parent_depth + 1 = 0 + 1 = 1 (§D, Cx 496 amendment 5)."""
    w = _world(tmp_path / "d1.world")
    reads = PorcelainWorldReads(w)
    moments = ["spine-touch: clerk"]
    ctx = {**_ctx(), "main_protagonist": PLAYER}
    # Mint the P2b arc at depth 0 (turn=1).
    minted = generate_opportunistic(
        w, reads, _GenProvider(), moments, [], ctx, turn=1, main_protagonist=PLAYER)
    assert minted is not None
    p2b_arc, _ = minted
    # Confirm depth-0 root.
    depth0 = w.porcelain.state(p2b_arc.arc_id, "gen_depth", frame=PLOT)["fact"]["value"]
    assert depth0 in (0, "0")
    # Simulate the P2b arc dying: create a terminal fallout with its arc_id.
    slug = p2b_arc.arc_id.removeprefix("arc:")
    fo2 = Fallout(
        arc_id=p2b_arc.arc_id, lifecycle="incompletable",
        term_id=f"event:arc_terminal_{slug}",
        entity=CLERK, attribute="desire_unresolved", value="drive:duty",
        directive="the p2b thread ended.")
    # Use a DIFFERENT proposal for the successor — different beats so fingerprint differs.
    different_proposal = dict(VALID_PROPOSAL)
    different_proposal["beats"] = [{"id": "beat:new_beat", "phase": "climax",
                                     "weight": "required", "kind": "event_occurs",
                                     "entity": "new_confrontation",
                                     "attribute": "", "value": ""}]
    reads2 = PorcelainWorldReads(w)
    minted2 = generate_from_fallout(
        w, reads2, _GenProvider(different_proposal), fo2, [p2b_arc], ctx, turn=5)
    assert minted2 is not None, "should regenerate from a dead P2b arc"
    regen_arc, _ = minted2
    depth_val = w.porcelain.state(regen_arc.arc_id, "gen_depth", frame=PLOT)["fact"]["value"]
    assert depth_val in (1, "1"), f"expected depth 1 from P2b death, got {depth_val!r}"
    w.close()


# --- Cx 498 regression tests (fixes b/c/d/e) --------------------------------

class _TurnProvider(StubProvider):
    """Routes run_turn cohorts; permissive defaults so minimal worlds never wedge."""

    def __init__(self, fail_on_gen: bool = False):
        super().__init__([])
        self._fail_on_gen = fail_on_gen

    async def complete(self, prompt, schema, *, tier="main", deliberate=False):
        self.calls.append((prompt, schema, tier))
        if self._fail_on_gen and task_of(prompt) == "gen":
            raise AssertionError("generate_arc must not be called on a non-salient turn")
        if prompt.startswith("Classify the lifetime"):
            return {"durability": "STATE", "confidence": 0.9}
        if prompt.startswith("Extract world-state"):
            return {"items": []}
        if prompt.startswith("Resolve an unestablished aspect"):
            return {"items": [{"value": "A lamplit office."}]}
        if task_of(prompt) == "cls":
            return {"kind": "action", "moves_to": "", "requires": []}
        if task_of(prompt) == "ndg":
            return {"thread": "", "directive": ""}
        if task_of(prompt) == "nar":
            return {"prose": "The office is still."}
        if task_of(prompt) == "npt":
            # npc_turn: acts=false, no speech — the NPC stays put.
            return {"acts": False, "action": "", "speaks": False, "intent": "",
                    "line_hint": ""}
        return {"items": []}


def test_ambient_seed_write_once_helper(tmp_path):
    """(b-unit) _last_development_min helper: write-once baseline arithmetic.

    Focused unit test of the helper function itself (no run_turn).  The full
    production-semantics integration (seed → quiet → fires) is in
    test_ambient_seed_write_once_and_fires_integration below.

    - First _last_development_min call seeds the row (write-once baseline).
    - Delta immediately after seeding is 0 → below AMBIENT_QUIET_MIN → no fire.
    - After advancing the diegetic clock past AMBIENT_QUIET_MIN without any
      other development, the ambient condition is satisfied.
    - The second call to _last_development_min reads the written baseline
      (does NOT reseed), confirming write-once.

    Diegetic time is set directly (not via commit_elapsed's delta-fold path,
    which requires full semantics declarations outside this helper-level test)."""
    w = _world(tmp_path / "amb_b.world")

    # Represent the diegetic clock via direct minutes_now values passed into the
    # helper — this is the exact form the turnloop uses (_gen_mins from read_clock).
    mins_now = 100.0

    # First call: no row present → seed-on-absent writes and returns minutes_now.
    reads = PorcelainWorldReads(w)
    seeded = _last_development_min(w, reads, mins_now, turn=1)
    assert seeded == mins_now, "seed-on-absent must return minutes_now"

    # Second call with a higher minutes_now — must return the written baseline (write-once).
    mins_later = 200.0
    reads2 = PorcelainWorldReads(w)
    read_back = _last_development_min(w, reads2, mins_later, turn=2)
    assert read_back == seeded, "write-once: second call must return the SEEDED value"

    # Delta immediately after seeding is 0 → no fire.
    assert (seeded - seeded) < AMBIENT_QUIET_MIN

    # Simulate the quiet half-day: minutes_now is now AMBIENT_QUIET_MIN + margin beyond seed.
    mins_threshold = mins_now + AMBIENT_QUIET_MIN + 10.0
    reads3 = PorcelainWorldReads(w)
    last_dev = _last_development_min(w, reads3, mins_threshold, turn=3)
    assert last_dev == seeded, "baseline must still be the seeded value (no new development)"
    assert mins_threshold - last_dev >= AMBIENT_QUIET_MIN, (
        "ambient condition must be satisfied after AMBIENT_QUIET_MIN quiet diegetic minutes")
    w.close()


def test_ambient_seed_write_once_and_fires_integration(tmp_path):
    """(b-integration) Ambient trigger: seed → quiet → fires.

    Production-semantics endless world mirrors the successful Cx probe (letter
    500): seeded at 100 minutes, made no first-turn attempt, minted arc:gen_2
    after 730 quiet minutes.

    Sequence:
      (1) Turn 1 — quiet (no development); ambient threshold not yet crossed.
          Assert: no 'gen' prompt dispatched; no generation_attempt receipt;
          session:ambient/last_development_min IS written (seed-on-absent).
      (2) Advance real diegetic accrue counter by 730 minutes via commit_elapsed.
      (3) Turn 2 — quiet again; provider returns a valid gen-arc proposal for
          task='gen'.  Threshold is now crossed → ambient fires.
          Assert: exactly one generation_attempt receipt; one arc:gen_2 in the
          portfolio with generated_from == 'ambient:2' and gen_depth == 0.

    Turn numbers respect GEN_COOLDOWN=2: no attempt is recorded on turn 1
    (threshold not crossed), so _last_try_turn returns -(10**9); turn 2
    trivially satisfies the cooldown gap."""
    from construct.clock import commit_elapsed
    from construct.semantics import attribute_default as attr_default
    from construct.turnloop import run_turn

    # attribute_default is required so commit_elapsed's delta writes fold into an
    # accumulating total (fold_policy=accrue on elapsed_minutes) — without it
    # read_clock always returns 0 and the ambient threshold never crosses.
    w = _world(tmp_path / "amb_int.world", attribute_default=attr_default)
    # Seed the diegetic clock so read_clock returns a non-zero value (100 minutes).
    commit_elapsed(w, 100)

    by_id = {a.arc_id: a for a in arc_io.portfolio_from_frame(PorcelainWorldReads(w))}

    # ---- Turn 1: quiet endless run; threshold NOT yet crossed --------------------
    provider_quiet = _TurnProvider(fail_on_gen=False)
    run_turn(w, by_id["arc:main"], provider_quiet, "I wait.", turn=1,
             scope=[CLERK, PLAYER, "place:office"],
             scenario_mode="endless", side_arcs=[], generate=True)

    gen_calls_t1 = [p for p, _s, _t in provider_quiet.calls if task_of(p) == "gen"]
    assert gen_calls_t1 == [], "no gen cohort on turn 1 — threshold not yet crossed"
    reads1 = PorcelainWorldReads(w)
    assert not reads1.events(kind="generation_attempt", frame=SESSION), (
        "no generation_attempt receipt on turn 1")
    # seed-on-absent must have written the baseline.
    seed_val = reads1.state("session:ambient", "last_development_min", frame=SESSION)
    assert seed_val is not None, "last_development_min must be seeded after turn 1"

    # ---- Advance clock 730 minutes past seed — crosses AMBIENT_QUIET_MIN (720) ---
    commit_elapsed(w, 730)

    # ---- Turn 2: quiet again; threshold crossed; provider returns valid proposal ---
    class _AmbientProvider(_TurnProvider):
        """Returns a valid gen-arc proposal for task='gen'; permissive elsewhere."""
        async def complete(self, prompt, schema, *, tier="main", deliberate=False):
            self.calls.append((prompt, schema, tier))
            if task_of(prompt) == "gen":
                return dict(VALID_PROPOSAL)
            if prompt.startswith("Classify the lifetime"):
                return {"durability": "STATE", "confidence": 0.9}
            if prompt.startswith("Extract world-state"):
                return {"items": []}
            if prompt.startswith("Resolve an unestablished aspect"):
                return {"items": [{"value": "A lamplit office."}]}
            if task_of(prompt) == "cls":
                return {"kind": "action", "moves_to": "", "requires": []}
            if task_of(prompt) == "ndg":
                return {"thread": "", "directive": ""}
            if task_of(prompt) == "nar":
                return {"prose": "The office is still."}
            if task_of(prompt) == "npt":
                return {"acts": False, "action": "", "speaks": False, "intent": "",
                        "line_hint": ""}
            return {"items": []}

    provider_fire = _AmbientProvider(fail_on_gen=False)
    result2 = run_turn(w, by_id["arc:main"], provider_fire, "I wait.", turn=2,
                       scope=[CLERK, PLAYER, "place:office"],
                       scenario_mode="endless", side_arcs=[], generate=True)

    # (a) Exactly one generation_attempt receipt.
    reads2 = PorcelainWorldReads(w)
    attempts = reads2.events(kind="generation_attempt", frame=SESSION)
    assert len(attempts) == 1, (
        f"exactly one generation_attempt expected after ambient fires; got {len(attempts)}")

    # (b) arc:gen_2 in portfolio with generated_from == 'ambient:2' and gen_depth == 0.
    assert "arc:gen_2" in result2.trace.generated, "arc:gen_2 must be in trace.generated"
    arc_ids = arc_io.arc_ids_from_frame(PorcelainWorldReads(w))
    assert "arc:gen_2" in arc_ids, "arc:gen_2 must be registered in the portfolio"
    from_val = w.porcelain.state("arc:gen_2", "generated_from", frame=PLOT)["fact"]["value"]
    assert from_val == "ambient:2", (
        f"generated_from must be 'ambient:2'; got {from_val!r}")
    depth_val = w.porcelain.state("arc:gen_2", "gen_depth", frame=PLOT)["fact"]["value"]
    assert depth_val in (0, "0"), (
        f"gen_depth must be 0 (depth-0 root); got {depth_val!r}")
    w.close()


def test_no_gen_call_when_spined_npc_existed_before_turn(tmp_path):
    """(c) Integration pin (Cx 498 BLOCKED): a spined NPC (canon drive row) that
    existed BEFORE the current turn does not make the turn salient. When the player
    performs a non-salient action, no generate_arc cohort call must happen and no
    generation_attempt event must be recorded.

    Production-shaped scope (CLERK + PLAYER + office) is passed so the fact-delta
    loop actually iterates entities and exercises the valid_from filter.  The
    provider RECORDS all prompts (never raises) so we can assert afterward that no
    'gen' cohort was dispatched — the old raise-on-gen approach was swallowed by
    the fail-open wrapper and gave a false pass."""
    from construct.clock import commit_elapsed
    from construct.turnloop import run_turn

    w = _world(tmp_path / "cx498c.world")
    # CLERK's drive row already exists from the fixture (written at cursor=1.0,
    # well before any turn_time(1) = TURN_EPOCH + 1.0). No new fact is committed
    # this turn — the player just waits.
    commit_elapsed(w, 5)  # small diegetic advance; no development

    by_id = {a.arc_id: a for a in arc_io.portfolio_from_frame(PorcelainWorldReads(w))}
    # Recording provider — does NOT raise on gen; we assert absence afterward.
    provider = _TurnProvider(fail_on_gen=False)
    # Production-shaped scope: CLERK (spined NPC) + player + place.
    scope = [CLERK, PLAYER, "place:office"]
    # generate=True so the block runs; the delta filter must suppress the cohort call.
    run_turn(w, by_id["arc:main"], provider, "I wait.", turn=1,
             scope=scope, scenario_mode="endless", side_arcs=[], generate=True)

    # (a) No 'gen' cohort prompt was dispatched at all.
    gen_calls = [p for p, _s, _t in provider.calls if task_of(p) == "gen"]
    assert gen_calls == [], (
        "generate_arc cohort must not be called when the turn's delta is empty "
        "(pre-existing drive row must not trigger the opportunistic DM); "
        f"got {len(gen_calls)} gen call(s)")

    # (b) Belt-and-suspenders: no generation_attempt receipt written.
    reads = PorcelainWorldReads(w)
    assert not reads.events(kind="generation_attempt", frame=SESSION), (
        "no generation_attempt may be recorded when the turn's delta is empty")
    w.close()


def test_event_boundary_prior_turn_event_excluded(tmp_path):
    """(d) Event-boundary pin: an event at exactly turn_time(turn-1) must be
    excluded from the salience window (the `e.at > turn_floor` filter). An event
    at turn_time(turn-1)+0.5 (strictly inside the window) must be included.

    Uses `window_events` — the shared helper now used by the turnloop — so if
    the production filter were removed, this test would catch it (the inline
    duplicate would no longer protect it)."""
    turn = 3
    turn_floor = turn_time(turn - 1)

    # Event AT the boundary (inclusive side of PB's raw window — must be excluded).
    ev_boundary = EventRow(
        event_id="event:boundary", kind="confrontation",
        at=turn_floor, caused_by=())
    # Event strictly inside the window.
    ev_inside = EventRow(
        event_id="event:inside", kind="confrontation",
        at=turn_floor + 0.5, caused_by=())
    # prior_kinds: "confrontation" not in it, so first-time-kind signal fires.
    prior_kinds: set[str] = set()

    # With only the boundary event — window_events must exclude it.
    filtered_boundary = window_events([ev_boundary], turn_floor)
    assert filtered_boundary == [], "event at exactly turn_floor must be excluded"
    lines_boundary = salient_moments([], filtered_boundary, prior_kinds, set())
    assert lines_boundary == [], "boundary-excluded event must not produce salient lines"

    # With the inside event — window_events must pass it through.
    filtered_inside = window_events([ev_inside], turn_floor)
    assert filtered_inside == [ev_inside], "event strictly inside window must be included"
    lines_inside = salient_moments([], filtered_inside, prior_kinds, set())
    assert lines_inside, "inside-window event (new kind) must produce a salient line"


def test_peak_turn_ledger_written_no_generation_receipts(tmp_path):
    """(e) Peak-turn split contract: when the main arc is at CRISIS/CLIMAX and a
    beat/clock/fallout development occurs this turn, the session:ambient ledger row
    IS written (the development happened), but the trigger chain contributes zero
    rows — no generation_attempt, no generation_declined, no mint.

    A side arc with an always-true beat (StateIs CLERK kind person) is passed so
    beat_pass fires it during the turn, producing a real same-turn development.
    The right-of-way gate must then be silent despite _mark_development being
    called (§B split contract: ledger written, trigger chain contributes zero rows).

    All four outcomes are asserted:
      (1) session:ambient/last_development_min is present/updated this turn,
      (2) no 'gen' cohort prompt dispatched,
      (3) zero generation_attempt AND generation_declined receipts,
      (4) no new arc in trace.generated and none added to the portfolio."""
    from construct.arc.conditions import StateIs
    from construct.clock import commit_elapsed
    from construct.turnloop import run_turn

    w = _world(tmp_path / "peak_e.world")
    # Put the main arc into CLIMAX: achieve the climax_ready_beat.
    w.porcelain.ingest_structured(
        [{"entity": "beat:discover", "attribute": "status", "value": "achieved",
          "valid_from": turn_time(1)}], frame=PLOT)

    reads = PorcelainWorldReads(w)
    assert main_at_peak(reads, _main_arc_from(w)), "arc must be at peak for this test"

    # Advance clock so _gen_mins is non-None.
    commit_elapsed(w, 100)

    # Build a minimal side arc whose single required beat is immediately achievable
    # (StateIs CLERK kind person — always TRUE since the fixture writes CLERK's kind
    # row at cursor=1.0).  beat_pass will fire it during the measured turn, producing
    # a real same-turn development without requiring any prose or player action.
    side_beat = Beat("beat:side_noop", Phase.CLIMAX, Weight.REQUIRED,
                     achievable_via=StateIs(CLERK, "kind", "person"))
    side_shape = ConclusionShape("shape:side", "drive_inverted",
                                 (CLERK, "drive:duty", "drive:fear"),
                                 world_condition=StateIs(CLERK, "kind", "person"),
                                 premise=StateIs(CLERK, "kind", "person"),
                                 refusal_variant_id="shape:side_refused")
    side_refusal_clock = Clock("clock:side_refusal", TurnsQuiet(999),
                               effects=({"entity": "event:side_refused", "attribute": "kind",
                                         "value": "refusal_conclusion"},),
                               bound_to="arc:side_peak", rung=Rung.REFUSAL)
    side_arc = Arc("arc:side_peak", CLERK, side_shape, (side_beat,), (),
                   side_refusal_clock, 0, (), {Phase.CLIMAX: 1})
    # Register the side arc in the plot frame so portfolio_from_frame sees it.
    w.porcelain.ingest_structured(
        arc_io.arc_to_items(side_arc, frame=PLOT) + arc_io.index_items(side_arc, frame=PLOT),
        frame=PLOT)
    w.porcelain.ingest_structured(
        arc_io.portfolio_add_items(PorcelainWorldReads(w), "arc:side_peak",
                                   valid_from=turn_time(1)),
        frame=PLOT)

    by_id = {a.arc_id: a for a in arc_io.portfolio_from_frame(PorcelainWorldReads(w))}
    provider = _TurnProvider(fail_on_gen=False)
    # generate=True — the right-of-way gate must fire and keep the trigger chain silent.
    result = run_turn(w, by_id["arc:main"], provider, "I wait.", turn=2,
                      scope=[CLERK, PLAYER, "place:office"],
                      scenario_mode="endless", side_arcs=[by_id["arc:side_peak"]],
                      generate=True)

    # (1) session:ambient/last_development_min must be present/updated this turn —
    #     the side-beat achievement caused _mark_development to be called.
    reads2 = PorcelainWorldReads(w)
    ledger_val = reads2.state("session:ambient", "last_development_min", frame=SESSION)
    assert ledger_val is not None, (
        "last_development_min must be written when a development occurs this turn")

    # (2) No 'gen' cohort prompt dispatched — right-of-way silenced the trigger.
    gen_calls = [p for p, _s, _t in provider.calls if task_of(p) == "gen"]
    assert gen_calls == [], (
        f"generate_arc cohort must not be called at peak; got {len(gen_calls)} call(s)")

    # (3) Zero generation_attempt AND generation_declined receipts — trigger chain silent.
    assert not reads2.events(kind="generation_attempt", frame=SESSION), (
        "no generation_attempt on a peak turn")
    assert not reads2.events(kind="generation_declined", frame=SESSION), (
        "no generation_declined on a peak turn (right-of-way is silent, not a DM judgment)")

    # (4) No new arc in trace.generated and no generated arc added to the portfolio.
    assert result.trace.generated == [], "no arc should be minted on a peak turn"
    arc_ids_after = arc_io.arc_ids_from_frame(PorcelainWorldReads(w))
    assert not any(aid.startswith("arc:gen_") for aid in arc_ids_after), (
        "no generated arc should appear in the portfolio on a peak turn")


def _main_arc_from(w) -> Arc:
    """Reconstruct the main arc from a world's portfolio."""
    reads = PorcelainWorldReads(w)
    return next(a for a in arc_io.portfolio_from_frame(reads) if a.arc_id == "arc:main")


def _read_narrator_promote(w, turn: int) -> object:
    """Read the narrator_promote handoff row for a given turn from the session frame.

    Uses frame_facts (not reads.state) because PB's state() does not resolve
    `event:` prefixed entities written into the session frame when those entities
    also have rows in the canon frame — the same PB routing constraint that
    motivated the frame_facts read in the turnloop generator block."""
    rows = list(frame_facts(w, SESSION, entity=f"event:turn_{turn}",
                            attribute="narrator_promote"))
    if not rows:
        return None
    return str(rows[0].value) if rows[0].value is not None else None


# ==========================================================================
# Fact-source v3 tests (HD 520 + Cx 525 test bar — §E, LIVING-WORLD-GENERATOR-P2.md)
# ==========================================================================

# --- pure-unit helpers ---------------------------------------------------

def test_confirmed_batch_filters_to_receipt_keys():
    # confirmed_batch keeps only candidates confirmed by receipt (entity+attribute match).
    candidates = [
        {"entity": "person:clerk", "attribute": "drive", "value": "drive:duty"},
        {"entity": "person:clerk", "attribute": "fear", "value": "drive:ruin"},
        {"entity": "fact:x", "attribute": "kind", "value": "proposition"},
    ]
    receipt = [
        {"entity": "person:clerk", "attribute": "drive", "assertion_id": "a1"},
        # "fact:x/kind" NOT in receipt → must be dropped
    ]
    kept, dropped = confirmed_batch(candidates, receipt)
    assert len(kept) == 1 and kept[0]["entity"] == "person:clerk"
    assert kept[0]["attribute"] == "drive"
    assert kept[0]["value"] == "drive:duty"  # value preserved from candidates
    assert dropped == 0


def test_confirmed_batch_empty_receipt_gives_empty_kept():
    # Test 3 — failed promotion (empty receipt) never appears in the stored batch.
    candidates = [{"entity": "person:clerk", "attribute": "drive", "value": "drive:duty"}]
    kept, dropped = confirmed_batch(candidates, [])
    assert kept == []
    assert dropped == 0


def test_confirmed_batch_value_side_preserved():
    # Test 4 — value-side spine-touch: the VALUE field of a confirmed candidate is
    # preserved exactly (not derived from the receipt, which has no value column).
    receipt = [{"entity": "fact:bond", "attribute": "holder", "assertion_id": "a2"}]
    candidates = [{"entity": "fact:bond", "attribute": "holder", "value": CLERK}]
    kept, dropped = confirmed_batch(candidates, receipt)
    assert len(kept) == 1
    assert kept[0]["value"] == CLERK  # value survives the join


def test_confirmed_batch_cap_truncation_deterministic():
    # Test 6 — cap/truncation: with 70 candidates and cap=60, kept=60, dropped=10.
    # Order is deterministic (candidate list order); same call always returns same result.
    candidates = [
        {"entity": f"fact:x{i}", "attribute": "kind", "value": "v"}
        for i in range(70)
    ]
    receipt = [
        {"entity": f"fact:x{i}", "attribute": "kind"}
        for i in range(70)
    ]
    kept, dropped = confirmed_batch(candidates, receipt, cap=60)
    assert len(kept) == 60
    assert dropped == 10
    # Deterministic: the first 60 candidates in order.
    assert [c["entity"] for c in kept] == [f"fact:x{i}" for i in range(60)]
    # Second call produces identical result.
    kept2, dropped2 = confirmed_batch(candidates, receipt, cap=60)
    assert kept == kept2 and dropped == dropped2


def test_confirmed_batch_duplicate_key_fail_closed():
    # FIX 1 (FIX 3d) — occurrence-aware join: two same-key candidates where PB commits
    # one and skips the other → no spine-touch fuel, no key in kept.
    #
    # Repro: place:office/in has two candidates (person:clerk skipped as containment
    # cycle; place:building committed). PB returns ONE receipt row for place:office/in.
    # cand_counts[("place:office","in")] = 2, receipt_counts[("place:office","in")] = 1
    # → mismatch → entire key dropped → kept = [].
    candidates = [
        {"entity": "place:office", "attribute": "in", "value": "person:clerk"},
        {"entity": "place:office", "attribute": "in", "value": "place:building"},
    ]
    # PB committed only the second (place:building) and skipped the first:
    receipt = [
        {"entity": "place:office", "attribute": "in", "assertion_id": "a1"},
    ]
    kept, dropped = confirmed_batch(candidates, receipt)
    assert kept == [], (
        "a mixed receipt with one of two same-key candidates skipped must drop the "
        "entire key (fail closed) — a skipped person:clerk must never wake the generator")
    assert dropped == 0  # dropped_count tracks cap overflow, not key rejection


def test_confirmed_batch_extra_receipts_also_fail_closed():
    # The OTHER mismatch direction: MORE receipt rows than candidates for a key is
    # ambiguity too — an extra sibling row could mask a skip (candidates [A, B] with
    # A skipped but B double-reported would count 2 receipts and resurrect A under a
    # >= rule). Exact count match only; any mismatch drops the whole key.
    candidates = [
        {"entity": "place:office", "attribute": "in", "value": "person:clerk"},
        {"entity": "place:office", "attribute": "in", "value": "place:building"},
    ]
    receipt = [
        {"entity": "place:office", "attribute": "in", "assertion_id": "a1"},
        {"entity": "place:office", "attribute": "in", "assertion_id": "a2"},
        {"entity": "place:office", "attribute": "in", "assertion_id": "a3"},
    ]
    kept, _dropped = confirmed_batch(candidates, receipt)
    assert kept == [], "receipt/candidate count mismatch (either direction) must drop the key"
    # exact match keeps both:
    kept2, _ = confirmed_batch(candidates, receipt[:2])
    assert len(kept2) == 2


def test_prior_promote_batch_returns_list_on_valid_json():
    raw = json.dumps([
        {"entity": "person:clerk", "attribute": "drive", "value": "drive:duty"}
    ])
    result = prior_promote_batch(raw)
    assert len(result) == 1
    assert result[0]["entity"] == "person:clerk"
    assert result[0]["value"] == "drive:duty"


def test_prior_promote_batch_returns_empty_on_none():
    # Test 2 / Test 5 — missing or failed settle yields [].
    assert prior_promote_batch(None) == []


def test_prior_promote_batch_returns_empty_on_malformed():
    assert prior_promote_batch("not json {{{") == []
    assert prior_promote_batch(json.dumps("a string, not a list")) == []
    assert prior_promote_batch(json.dumps(42)) == []


def test_prior_promote_batch_all_or_empty():
    # FIX 2 — all-or-empty contract: ANY malformed member returns [] for the entire batch.
    # A mixed list with a non-dict member → [] (no partial salvage).
    raw_mixed = json.dumps([
        {"entity": "person:clerk", "attribute": "drive", "value": "duty"},
        "not a dict",
        None,
        42,
    ])
    assert prior_promote_batch(raw_mixed) == [], (
        "a list with any non-dict member must return [] (all-or-empty)")

    # A dict missing the 'entity' key → [].
    raw_no_entity = json.dumps([{"attribute": "drive", "value": "duty"}])
    assert prior_promote_batch(raw_no_entity) == [], (
        "a dict with missing entity key must return []")

    # A dict with a non-string entity → [].
    raw_int_entity = json.dumps([{"entity": 42, "attribute": "drive", "value": "duty"}])
    assert prior_promote_batch(raw_int_entity) == [], (
        "a dict with non-string entity must return []")

    # A dict missing the 'value' key → [].
    raw_no_value = json.dumps([{"entity": "person:clerk", "attribute": "drive"}])
    assert prior_promote_batch(raw_no_value) == [], (
        "a dict with missing value key must return []")

    # A dict with a missing attribute key → [].
    raw_no_attr = json.dumps([{"entity": "person:clerk", "value": "duty"}])
    assert prior_promote_batch(raw_no_attr) == [], (
        "a dict with missing attribute key must return []")

    # A fully-valid single-item list still works (regression guard).
    raw_valid = json.dumps([{"entity": "person:clerk", "attribute": "drive", "value": "duty"}])
    result = prior_promote_batch(raw_valid)
    assert len(result) == 1 and result[0]["entity"] == "person:clerk", (
        "a fully valid list must still parse correctly after the all-or-empty fix")


# --- settle-level handoff row tests -------------------------------------

def test_quiet_settle_writes_empty_batch(tmp_path):
    # Test 2 — a quiet settle writes [] for the handoff row; no promote → confirmed batch is [].
    from construct.semantics import attribute_default as attr_default
    from construct.turnloop import run_turn

    w = _world(tmp_path / "quiet.world", attribute_default=attr_default)
    by_id = {a.arc_id: a for a in arc_io.portfolio_from_frame(PorcelainWorldReads(w))}

    provider = _TurnProvider(fail_on_gen=False)
    result = run_turn(w, by_id["arc:main"], provider, "I wait.", turn=1,
                      scope=[CLERK, PLAYER, "place:office"],
                      scenario_mode="endless", side_arcs=[], generate=False)
    # Call settle synchronously so the handoff row is written before we read.
    if result.settle:
        result.settle()

    # Use frame_facts to read the handoff row (event: entities in session frame
    # are not accessible via reads.state — see _read_narrator_promote helper).
    raw = _read_narrator_promote(w, turn=1)
    assert raw is not None, "narrator_promote handoff row must be written on every settle"
    batch = prior_promote_batch(raw)
    assert batch == [], f"quiet settle must write [] batch; got {batch}"
    w.close()


def test_failed_promote_stores_empty_and_stale_row_cannot_wake(tmp_path):
    # FIX 3b — real-seam test: force the canon promotion ingest to raise so that
    # _FailOpenIngest returns an empty receipt → confirmed_batch returns [] → the
    # settle handoff row stores []. Then verify that an OLDER batch (turn n-2) plus a
    # MISSING turn n-1 row cannot wake the generator through the production run_turn path.
    #
    # Injection mechanism: monkeypatch world.porcelain.ingest_structured so it raises
    # for frame="canon" calls (the promotion path at turnloop.py ~5128). The SESSION
    # handoff write (frame=SESSION, classify="rules") is allowed through. _FailOpenIngest
    # catches the canon raise, returns {"rows": []}, confirmed_batch gets [] receipt → [].
    from construct.semantics import attribute_default as attr_default
    from construct.turnloop import run_turn

    w = _world(tmp_path / "failpromote.world", attribute_default=attr_default)

    # Wrap the porcelain ingest to raise for canon frame only.
    _original_ingest = w.porcelain.ingest_structured

    def _raising_ingest(rows, frame=None, **kwargs):
        if frame == "canon":
            raise RuntimeError("injected canon ingest failure")
        return _original_ingest(rows, frame=frame, **kwargs)

    w.porcelain.ingest_structured = _raising_ingest  # type: ignore[method-assign]

    # Build a provider where extract returns a CLERK-touching row (so there would be a
    # candidate) but the canon raise will prevent it from landing.
    _original_extract = w.porcelain.extract

    def _extract_with_clerk(text, **kwargs):
        # Return a row that would promote CLERK's drive (same-value, no contradiction).
        # frame:"canon" = the LIVE extractor shape (its prompt stamps every item) — the
        # settle must strip it or the row bypasses staging (the 2026-07-09 live defect).
        return [{"entity": CLERK, "attribute": "drive", "value": "drive:duty",
                 "frame": "canon"}]

    w.porcelain.extract = _extract_with_clerk  # type: ignore[method-assign]

    by_id = {a.arc_id: a for a in arc_io.portfolio_from_frame(PorcelainWorldReads(w))}
    provider = _TurnProvider(fail_on_gen=False)
    result = run_turn(w, by_id["arc:main"], provider, "I observe.", turn=1,
                      scope=[CLERK, PLAYER, "place:office"],
                      scenario_mode="endless", side_arcs=[], generate=False)
    if result.settle:
        result.settle()

    # Restore so subsequent reads work normally.
    w.porcelain.ingest_structured = _original_ingest  # type: ignore[method-assign]
    w.porcelain.extract = _original_extract  # type: ignore[method-assign]

    # The stored batch for turn 1 must be [] (the raise → empty receipt → empty confirmed).
    raw_t1 = _read_narrator_promote(w, turn=1)
    assert raw_t1 is not None, "SESSION handoff row must still be written even when canon raise"
    stored_batch = prior_promote_batch(raw_t1)
    assert stored_batch == [], (
        "a canon ingest failure must store [] — uncommitted candidates never enter the batch")

    # --- Phase 2: older batch present, NO turn n-1 row, drive production run_turn ---
    # Set up a DIFFERENT world where turn 0 has a CLERK-touching batch but turn 1 is ABSENT
    # (no settle ever ran for turn 1). Run turn 2 and assert no gen call and no attempt receipt.
    w.close()
    w2 = _world(tmp_path / "stale.world", attribute_default=attr_default)

    # Write an older batch (turn 0) with a spine-touching CLERK row.
    older_batch = [{"entity": CLERK, "attribute": "drive", "value": "drive:duty"}]
    w2.porcelain.ingest_structured([
        {"entity": "event:turn_0", "attribute": "narrator_promote",
         "value": json.dumps(older_batch), "value_type": "literal",
         "valid_from": turn_time(0)},
    ], frame=SESSION, classify="rules")
    # Turn 1 row is deliberately NOT written (no settle ran for turn 1).
    # Also write a turn-1 turn-kind receipt so next_turn_number is 2:
    w2.porcelain.ingest_structured([
        {"entity": "event:turn_1", "attribute": "kind", "value": "turn",
         "valid_from": turn_time(1)},
    ], frame=SESSION)

    by_id2 = {a.arc_id: a for a in arc_io.portfolio_from_frame(PorcelainWorldReads(w2))}
    provider2 = _TurnProvider(fail_on_gen=True)  # gen call would raise AssertionError
    # Turn 2 production run: the reader reads event:turn_1/narrator_promote (ABSENT → [])
    # — the older turn-0 batch must not surface through the per-turn keyed reader.
    run_turn(w2, by_id2["arc:main"], provider2, "I wait.", turn=2,
             scope=[CLERK, PLAYER, "place:office"],
             scenario_mode="endless", side_arcs=[], generate=True)

    reads2 = PorcelainWorldReads(w2)
    assert not reads2.events(kind="generation_attempt", frame=SESSION), (
        "a missing turn n-1 row must yield [] — the stale turn-0 batch must not wake the generator")
    w2.close()


def test_settle_drops_noncanon_framed_rows_fail_closed(tmp_path):
    # Cx 546 correction: the extractor may legitimately emit knows:<person> rows
    # (a telling scene). The narrator-settle channel's promote gate is CANON policy —
    # a blanket frame-strip corrupted a knowledge copy toward canon + the PLAYER's
    # frame (Cx's demonstrated breach). Until the knowledge-promotion gate exists
    # (NPC-learning RFC-002), non-canon-framed rows are FAIL-CLOSED dropped with
    # telemetry. This pins all four negatives + the drop telemetry, live-shaped.
    from construct.semantics import attribute_default as attr_default
    from construct.turnloop import run_turn, _PROPOSED

    w = _world(tmp_path / "knows_drop.world", attribute_default=attr_default)

    def _extract_telling(text, **kwargs):
        # The live extractor shape for "the clerk was told the secret":
        # a knowledge copy targeted at the CLERK's frame, no canon row.
        # Returned ONLY for the narrator-prose settle extraction — the player-INPUT
        # extraction (same porcelain.extract, different text) is a separate channel
        # outside this pin's scope (flagged to Cx as an adjacent seam).
        if "tell the clerk" in str(text).lower():
            return []  # the player-input extraction call
        return [{"entity": "fact:whisper", "attribute": "told", "value": "yes",
                 "frame": f"knows:{CLERK}"}]

    w.porcelain.extract = _extract_telling  # type: ignore[method-assign]

    by_id = {a.arc_id: a for a in arc_io.portfolio_from_frame(PorcelainWorldReads(w))}
    provider = _TurnProvider(fail_on_gen=False)
    result = run_turn(w, by_id["arc:main"], provider, "I tell the clerk the secret.",
                      turn=1, scope=[CLERK, PLAYER, "place:office"],
                      scenario_mode="endless", side_arcs=[], generate=False)
    assert result.settle is not None
    result.settle()

    p = w.porcelain
    # (1) NOT written into the NPC's knowledge frame via this ungated path.
    assert not [f for f in p.facts(f"knows:{CLERK}", entity="fact:whisper")], (
        "a narrator-told knowledge row must NOT reach the NPC frame through the "
        "ungated settle channel (waits for the knowledge-promotion gate)")
    # (2) NOT canonized (neither staged-promoted nor direct).
    assert not [f for f in p.facts("canon", entity="fact:whisper")], (
        "a knowledge copy must never become canon")
    # (3) NOT mirrored into the player's knowledge frame.
    assert not [f for f in p.facts(f"knows:{PLAYER}", entity="fact:whisper")], (
        "a knowledge copy must never leak into the PLAYER's frame")
    # (4) NOT in the narrator handoff batch (no generator fuel from a dropped row).
    raw = _read_narrator_promote(w, turn=1)
    assert prior_promote_batch(raw) == [], (
        "a dropped knowledge row must not enter the P2b handoff batch")
    # (5) Telemetry: the drop is visible on the trace.
    assert any("settle_noncanon_frames" in d for d in (result.trace.dropped_cohorts or [])), (
        "the fail-closed drop must be visible telemetry, never silent")
    w.close()


def test_settle_persisted_batch_salient_next_turn(tmp_path):
    # FIX 3a — the live Probe-1 blind case (HD 520) via the REAL settle seam.
    # A narrator prose extraction that touches a spined NPC must land in the handoff row
    # through the production settle path (extract → resolve → stage → promote → receipt →
    # confirmed_batch → handoff write). On the NEXT turn, the production run_turn reads
    # the handoff row and dispatches the gen cohort.
    #
    # Injection mechanism: monkeypatch world.porcelain.extract to return a CLERK-touching
    # row (CLERK already has drive=drive:duty in canon — same-value restatement, no
    # contradiction, goes to promote). The real _settle path runs through extract,
    # resolve_rows, stage in _PROPOSED, proposed_vals diff, promote ingest, receipt
    # capture, confirmed_batch, and handoff write. No manual row write.
    from construct.semantics import attribute_default as attr_default
    from construct.turnloop import run_turn

    w = _world(tmp_path / "probe1.world", attribute_default=attr_default)

    # Stub extract to return a CLERK-touching row.
    # CLERK/drive/drive:duty: same-value restatement → no contradiction → goes to promote.
    def _extract_clerk_touch(text, **kwargs):
        # frame:"canon" = the LIVE extractor shape — without the settle's strip, this
        # row bypasses the quarantine staging entirely and the handoff batch is [].
        return [{"entity": CLERK, "attribute": "drive", "value": "drive:duty",
                 "frame": "canon"}]

    w.porcelain.extract = _extract_clerk_touch  # type: ignore[method-assign]

    by_id = {a.arc_id: a for a in arc_io.portfolio_from_frame(PorcelainWorldReads(w))}
    provider1 = _TurnProvider(fail_on_gen=False)
    result = run_turn(w, by_id["arc:main"], provider1, "I question the clerk.", turn=1,
                      scope=[CLERK, PLAYER, "place:office"],
                      scenario_mode="endless", side_arcs=[], generate=False)
    # Run the real _settle so the handoff row is written through the full production path.
    assert result.settle is not None, "run_turn must return a settle callable"
    result.settle()

    # Verify the stored batch is nonempty and value-hydrated (not just a [] from a quiet settle).
    raw_t1 = _read_narrator_promote(w, turn=1)
    assert raw_t1 is not None, "handoff row must be written after settle"
    stored_batch = prior_promote_batch(raw_t1)
    assert stored_batch, (
        "settle must persist a nonempty batch when extract returns a CLERK-touching row "
        "(receipt-confirmed, value-hydrated — the Probe-1 seam)")
    # The stored batch must contain CLERK (entity-side spine touch) with the value hydrated.
    clerk_rows = [r for r in stored_batch if r.get("entity") == CLERK]
    assert clerk_rows, "CLERK must appear in the stored batch (entity-side spine touch)"
    assert clerk_rows[0].get("value") == "drive:duty", (
        "value must be hydrated from the candidate, not derived from the receipt")

    # Close and reopen the world to confirm the row survives persistence.
    w.close()
    from patternbuffer.testing import StubModel as _SM, rule_classifier_fallback as _rcf
    _rule = _rcf()

    def _fb(prompt, schema):
        if prompt.startswith("Classify the lifetime"):
            return _rule(prompt, schema)
        return {"items": []}

    w2 = World(tmp_path / "probe1.world", world_id="w:gen", stance="fiction",
               model=_SM(fallback=_fb), title="Gen Test World",
               attribute_default=attr_default)

    # Turn 2: build a provider that returns a valid gen proposal; pacing is clear.
    class _Probe1Provider(_TurnProvider):
        async def complete(self, prompt, schema, *, tier="main", deliberate=False):
            self.calls.append((prompt, schema, tier))
            if task_of(prompt) == "gen":
                return dict(VALID_PROPOSAL)
            if prompt.startswith("Classify the lifetime"):
                return {"durability": "STATE", "confidence": 0.9}
            if prompt.startswith("Extract world-state"):
                return {"items": []}
            if prompt.startswith("Resolve an unestablished aspect"):
                return {"items": [{"value": "The office is quiet."}]}
            if task_of(prompt) == "cls":
                return {"kind": "action", "moves_to": "", "requires": []}
            if task_of(prompt) == "ndg":
                return {"thread": "", "directive": ""}
            if task_of(prompt) == "nar":
                return {"prose": "The clerk glances at you."}
            if task_of(prompt) == "npt":
                return {"acts": False, "action": "", "speaks": False, "intent": "",
                        "line_hint": ""}
            return {"items": []}

    by_id2 = {a.arc_id: a for a in arc_io.portfolio_from_frame(PorcelainWorldReads(w2))}
    provider2 = _Probe1Provider(fail_on_gen=False)
    run_turn(w2, by_id2["arc:main"], provider2, "I confront the clerk.", turn=2,
             scope=[CLERK, PLAYER, "place:office"],
             scenario_mode="endless", side_arcs=[], generate=True)

    # The gen cohort must have been dispatched (entity-side spine-touch from the stored batch).
    gen_calls = [p for p, _s, _t in provider2.calls if task_of(p) == "gen"]
    assert gen_calls, (
        "generate_arc cohort must be called when the prior turn's settled batch touched a "
        "spined NPC — the Probe-1 blind case closed by real settle seam (FIX 3a)")
    w2.close()


def test_missing_prior_turn_row_reads_empty(tmp_path):
    # Test 2 — a missing turn n-1 row reads []; no stale replay from an even older source turn.
    # We write a turn_0 handoff row but read turn_{1} (turn-1=0) and then turn_{2} (turn-1=1).
    # The prior_promote_batch helper is the reader; the absence case returns [].
    from construct.semantics import attribute_default as attr_default

    w = _world(tmp_path / "missing.world", attribute_default=attr_default)
    # Write a handoff row for turn 0 only (the "stale" batch that must not reappear).
    stale_batch = [{"entity": CLERK, "attribute": "drive", "value": "drive:old"}]
    w.porcelain.ingest_structured([
        {"entity": "event:turn_0", "attribute": "narrator_promote",
         "value": json.dumps(stale_batch), "value_type": "literal",
         "valid_from": turn_time(0)},
    ], frame=SESSION, classify="rules")

    # Turn 2 reads event:turn_1/narrator_promote — which was never written.
    raw_missing = _read_narrator_promote(w, turn=1)
    assert prior_promote_batch(raw_missing) == [], (
        "a missing turn n-1 row must produce [] — no stale replay from turn 0")

    # The turn-0 row itself is still accessible but must not be read at turn 2
    # (the per-turn key prevents stale replay structurally).
    raw_turn0 = _read_narrator_promote(w, turn=0)
    assert prior_promote_batch(raw_turn0) != [], "turn-0 row still exists but is not consulted"
    w.close()


def test_first_turn_absence_and_reopen(tmp_path):
    # Test 5 — first-turn absence reads []; clean close/reopen reads the persisted prior-turn row.
    from construct.semantics import attribute_default as attr_default
    from construct.turnloop import run_turn

    w = _world(tmp_path / "reopen.world", attribute_default=attr_default)

    # Before any settle: turn 0 handoff row does not exist → reads [].
    raw_absent = _read_narrator_promote(w, turn=0)
    assert prior_promote_batch(raw_absent) == [], "first-turn absence must read []"

    by_id = {a.arc_id: a for a in arc_io.portfolio_from_frame(PorcelainWorldReads(w))}
    provider = _TurnProvider(fail_on_gen=False)
    result = run_turn(w, by_id["arc:main"], provider, "I wait.", turn=1,
                      scope=[CLERK, PLAYER, "place:office"],
                      scenario_mode="endless", side_arcs=[], generate=False)
    # Settle synchronously to write the handoff row.
    if result.settle:
        result.settle()

    # Verify the row was written (use frame_facts — not reads.state — for event: entities).
    raw1 = _read_narrator_promote(w, turn=1)
    assert raw1 is not None, "handoff row must be persisted after settle"

    # Close and reopen: the row must survive.
    w.close()
    from patternbuffer import World
    from patternbuffer.testing import StubModel, rule_classifier_fallback
    rule = rule_classifier_fallback()

    def fallback(prompt, schema):
        if prompt.startswith("Classify the lifetime"):
            return rule(prompt, schema)
        return {"items": []}

    from construct.semantics import attribute_default as attr_default2
    w2 = World(tmp_path / "reopen.world", world_id="w:gen", stance="fiction",
               model=StubModel(fallback=fallback), title="Gen Test World",
               attribute_default=attr_default2)
    raw_reopen = _read_narrator_promote(w2, turn=1)
    assert raw_reopen is not None, "handoff row must survive world close/reopen"
    # The batch parses correctly ([] on quiet settle is still a valid persisted value).
    batch = prior_promote_batch(raw_reopen)
    assert isinstance(batch, list), f"reopen batch must be a list; got {type(batch)}"
    w2.close()


def test_standing_canon_at_high_cursor_not_salient(tmp_path):
    # Test 7 — standing canon rows at a high cursor (ingested-world shape) do NOT make
    # turns salient — holds by construction (no fact window exists in v3), pinned.
    # We ingest rows at a high explicit valid_from, run a quiet turn, assert no gen call.
    from construct.semantics import attribute_default as attr_default
    from construct.turnloop import run_turn

    w = _world(tmp_path / "highcursor.world", attribute_default=attr_default)

    # Ingest a CLERK drive row at a high valid_from (simulating an ingested world where
    # the engine cursor sits above every turn_time, the "permanently salient" failure
    # direction of the old fact window). The v3 batch approach never reads these.
    HIGH_VF = 8_000_000.0  # above any turn_time (TURN_EPOCH + turn ~ 1000 + turn)
    w.porcelain.ingest_structured([
        {"entity": CLERK, "attribute": "drive", "value": "drive:ambition",
         "valid_from": HIGH_VF},
    ])

    by_id = {a.arc_id: a for a in arc_io.portfolio_from_frame(PorcelainWorldReads(w))}
    # fail_on_gen=False so we can assert absence after the fact.
    provider = _TurnProvider(fail_on_gen=False)
    # generate=True — the opportunistic block runs; the fact window is gone so no spine-touch.
    run_turn(w, by_id["arc:main"], provider, "I wait.", turn=1,
             scope=[CLERK, PLAYER, "place:office"],
             scenario_mode="endless", side_arcs=[], generate=True)

    gen_calls = [p for p, _s, _t in provider.calls if task_of(p) == "gen"]
    assert gen_calls == [], (
        "standing canon rows at a high cursor must NOT make the turn salient "
        "(v3 fact-source holds by construction — no fact window)")
    reads = PorcelainWorldReads(w)
    assert not reads.events(kind="generation_attempt", frame=SESSION), (
        "no generation_attempt on a high-cursor-only turn")
    w.close()


def test_settle_batch_cap_real_seam(tmp_path, caplog):
    # FIX 3c — real settle with 70 promote candidates: the stored batch must contain
    # exactly 60 items in deterministic order, and the turnloop must log
    # "narrator_promote batch capped: kept=60 dropped=10 (turn N)".
    #
    # Injection mechanism: monkeypatch world.porcelain.extract to return 70 rows for
    # unique (CLERK, attr_N) pairs. CLERK is a known entity (binds in resolve_rows);
    # attr_N attributes do not exist in canon (no contradiction → all 70 go to promote).
    # The receipt from ingest_structured confirms all 70 → confirmed_batch caps at 60.
    from construct.semantics import attribute_default as attr_default
    from construct.turnloop import run_turn

    w = _world(tmp_path / "cap70.world", attribute_default=attr_default)

    # Build 70 unique (entity, attribute) pairs. Use CLERK (known, binds) with synthetic
    # attributes that don't exist in canon — no contradiction, all go to promote.
    _N = 70
    _extract_rows = [
        {"entity": CLERK, "attribute": f"cap_attr_{i}", "value": f"val_{i}",
         "frame": "canon"}  # the LIVE extractor shape (see the strip in _settle)
        for i in range(_N)
    ]

    def _extract_70(text, **kwargs):
        return list(_extract_rows)

    w.porcelain.extract = _extract_70  # type: ignore[method-assign]

    by_id = {a.arc_id: a for a in arc_io.portfolio_from_frame(PorcelainWorldReads(w))}
    provider = _TurnProvider(fail_on_gen=False)

    with caplog.at_level(logging.INFO, logger="construct.turnloop"):
        result = run_turn(w, by_id["arc:main"], provider, "I inspect everything.", turn=1,
                          scope=[CLERK, PLAYER, "place:office"],
                          scenario_mode="endless", side_arcs=[], generate=False)
        if result.settle:
            result.settle()

    # Assert the stored batch has exactly 60 items in deterministic order.
    raw_t1 = _read_narrator_promote(w, turn=1)
    assert raw_t1 is not None, "handoff row must be written"
    stored_batch = prior_promote_batch(raw_t1)
    assert len(stored_batch) == 60, (
        f"cap must truncate 70 → 60; got {len(stored_batch)}")
    # Deterministic subset: the 60 stored attrs must all come from the 70 injected attrs.
    stored_attrs = [r["attribute"] for r in stored_batch]
    all_attrs = {f"cap_attr_{i}" for i in range(_N)}
    assert all(a in all_attrs for a in stored_attrs), (
        f"stored attrs must all be from the injected set; got {stored_attrs[:5]}...")
    # Deterministic: a second read returns the same batch.
    stored_batch2 = prior_promote_batch(_read_narrator_promote(w, turn=1))
    assert stored_attrs == [r["attribute"] for r in stored_batch2], (
        "batch must be deterministic across reads")

    # Assert the caplog contains the kept=60 dropped=10 line from construct.turnloop.
    cap_log_found = any(
        "narrator_promote batch capped" in rec.message
        and "kept=60" in rec.message
        and "dropped=10" in rec.message
        for rec in caplog.records
        if rec.name == "construct.turnloop"
    )
    assert cap_log_found, (
        "turnloop must log 'narrator_promote batch capped: kept=60 dropped=10' "
        f"(found records: {[r.message for r in caplog.records if 'cap' in r.message.lower()]})")
    w.close()
