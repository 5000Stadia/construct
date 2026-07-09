"""The opportunistic DM generator — P2a (regenerative trigger + the six guards).

Drives `generate_from_fallout` directly (deterministic) with a stub provider that
returns a valid arc proposal, then exercises each guard: pacing cooldown, active
cap, fingerprint dedupe, depth cap, coherence preflight. Plus a full run_turn
integration test: a side arc dies and the world mints a grounded successor.
"""

import json

from patternbuffer import World
from patternbuffer.testing import StubModel, rule_classifier_fallback

from construct.adapter import PorcelainWorldReads
from construct.arc import generator as gen
from construct.arc import io as arc_io
from construct.arc.conditions import InFrame, StateIs, TurnsQuiet
from construct.arc.executor import PLOT, SESSION, Fallout, turn_time
from construct.arc.generator import generate_from_fallout
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
