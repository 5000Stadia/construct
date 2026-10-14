"""The atomic main-arc swap (arc audit F3, world audit B5): `game.continue_episode` and
`arc_io.replan_main_arc` commit their whole write phase as ONE pattern-buffer
`commit_set`, so a reader sees the old manifest + arc or the new ones, never no manifest
and never half an arc.

The failure tests inject the fault INSIDE the engine's atomic unit: the per-op
application (`Ingestor._ingest_item` for an assert, `TruthMaintenance.retract` for a
retract) raises, or gate-skips, when it reaches the chosen op. Each test proves the unit
had already staged rows before the fault, then that the slot is exactly what it was:
same visible rows, same verified manifest (the same assertion ids), same arc rows, no
settled marks, no time jump, no staged cast.
"""

import json
import shutil

import pytest
from patternbuffer import AtomicAbort, World
from patternbuffer.ingest import Ingestor
from patternbuffer.porcelain import Porcelain
from patternbuffer.testing import StubModel, rule_classifier_fallback
from patternbuffer.tmaint import TruthMaintenance

from construct import game
from construct.adapter import PorcelainWorldReads
from construct.arc import executor
from construct.arc import io as arc_io
from construct.arc.executor import PLOT, SESSION
from construct.clock import read_clock
from construct.provider import StubProvider, task_of
from construct.semantics import attribute_default
from construct.tangent import read_portfolio_state

PLAYER = "person:player"
NEW_HOOK = "person:shawl_witness"   # staged fresh: kind/name/role/in rows
OLD_HOOK = "person:ada"             # already canon: only an `in` row

_rule = rule_classifier_fallback()


def _fb(prompt, schema):
    """Durability for the BUILD-time rows: the manifest is CONSTITUTIVE (the live Cx 167
    condition, where a bare append is ignored after reopen), everything else by rule."""
    if prompt.startswith("Classify the lifetime"):
        if "arc:portfolio" in prompt:
            return {"durability": "CONSTITUTIVE", "class_confidence": 0.95}
        return _rule(prompt, schema)
    return {"items": []}


_PROPOSAL = {
    "protagonist": PLAYER, "delta_type": "desire_at_cost",
    "tension": [PLAYER, "drive:duty", "drive:fear"],
    "beats": [{"id": "beat:next", "phase": "climax", "weight": "required",
               "kind": "event_occurs", "entity": "confrontation",
               "attribute": "", "value": ""}],
    "hook": "A stranger waits on the stair.", "title": "The Weight of Brass",
    "hook_cast": [{"id": NEW_HOOK, "name": "Wren Shaw", "role": "frightened witness"},
                  {"id": OLD_HOOK, "name": "Ada Finch", "role": "an old friend"}],
    "thread_disposition": [{"index": 0, "disposition": "closed", "how": "the brother is cleared offstage"}],
    "responds_to_outcome": {"how": "the witness the last case spared comes looking",
                            "ids": [NEW_HOOK]},
}


class _Provider(StubProvider):
    """gen -> the proposal; dpol -> a policy; pth -> one personal thread."""

    def __init__(self, proposal=None):
        super().__init__([])
        self._proposal = proposal or _PROPOSAL

    async def complete(self, prompt, schema, *, tier="main", deliberate=False):
        self.calls.append((prompt, schema, tier))
        if prompt.startswith("Classify the lifetime"):
            return _fb(prompt, schema)
        if task_of(prompt) == "gen":
            return json.loads(json.dumps(self._proposal))
        if "Decide the DEATH POLICY" in prompt:
            return {"policy": "mortal", "reason": "test"}
        if task_of(prompt) == "pth":
            return {"threads": [{"thread": "promised Ada to clear her brother's name",
                                 "status": "open"}]}
        return {"items": []}


def _open(path, name):
    return World(path, world_id=f"w:{name}", stance="fiction",
                 attribute_default=attribute_default, model=StubModel(fallback=_fb))


def _make_slot(tmp_path, monkeypatch, name="atom"):
    """A played, CONCLUDED slot that exercises every write of the continuation: a sealed
    CONSTITUTIVE manifest (two retracts), a story that ended on the roof (the doorway
    place), no clock yet (the time jump stages kind + baseline + delta), one hook person
    already canon and one new, an unsurfaced consequence (the callback receipt), and a
    narrative ledger (the personal-threads record)."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "worlds").mkdir()
    spath = tmp_path / "worlds" / f"{name}.world"
    w = _open(spath, name)
    w.ingestor.cursor.advance(1.0)
    w.ingest_structured([
        {"entity": "place:office", "attribute": "kind", "value": "room", "timeless": True},
        {"entity": "place:roof", "attribute": "kind", "value": "room", "timeless": True},
        {"entity": PLAYER, "attribute": "kind", "value": "person", "timeless": True},
        {"entity": OLD_HOOK, "attribute": "kind", "value": "person", "timeless": True},
        {"entity": OLD_HOOK, "attribute": "in", "value": "place:office"},
        {"entity": PLAYER, "attribute": "in", "value": "place:office", "valid_from": 1000.4},
    ])
    w.porcelain.ingest_structured([
        {"entity": PLAYER, "attribute": "in", "value": "place:roof", "valid_from": 1005.0},
        {"entity": "event:consequence_word_5", "attribute": "kind",
         "value": "word_spreads", "valid_from": 1005.0},
        {"entity": "event:consequence_word_5", "attribute": "detail",
         "value": "word of who found it travels", "valid_from": 1005.0},
    ])
    arc = game._build_arc({**_PROPOSAL, "title": "First"}, arc_id="arc:main")
    w.porcelain.ingest_structured(arc_io.arc_to_items(arc) + arc_io.index_items(arc))
    w.porcelain.ingest_structured(
        arc_io.portfolio_items(["arc:main"], main_arc_id="arc:main"), frame=PLOT)
    w.porcelain.ingest_structured([
        {"entity": "event:turn_0", "attribute": "kind", "value": "turn", "valid_from": 1000.0},
        {"entity": "event:turn_5", "attribute": "kind", "value": "turn", "valid_from": 1005.0},
        {"entity": "event:arc_outcome_5", "attribute": "kind", "value": "arc_won",
         "valid_from": 1005.0},
        {"entity": "session:narrative_memory", "attribute": "text",
         "value": "You promised Ada you would clear her brother's name.",
         "value_type": "literal", "valid_from": 1005.0},
    ], frame=SESSION)
    w.close()
    spath.with_suffix(".meta.json").write_text(json.dumps(
        {"title": "First", "protagonist": PLAYER, "arc_scope": [PLAYER], "mode": "pure",
         "scenario_mode": "win_loss", "genre": "cozy", "death_policy": "shielded"}))
    shutil.copyfile(spath, game.slot_path(name, "u1"))
    return name


def _snapshot(name):
    """Everything a reader of the slot could see, read from a fresh handle."""
    w = _open(game.slot_path(name, "u1"), name)
    try:
        reads = PorcelainWorldReads(w)
        return {
            "head": w.buffer.head(),
            "rows": sorted((r.id, r.entity, r.attribute, repr(r.value), r.frame)
                           for r in w.buffer.visible()),
            "portfolio": read_portfolio_state(reads),
            "main_arc": arc_io.main_arc_from_frame(reads),
            "arc_ids": arc_io.arc_ids_from_frame(reads),
            "minutes": read_clock(w).minutes,
        }
    finally:
        w.close()


def _spy_writes(mp):
    """Record every porcelain write verb (with its kwargs) while `mp` is active."""
    calls: list[tuple[str, dict]] = []
    for verb in ("ingest_structured", "retract", "commit_set"):
        real = getattr(Porcelain, verb)

        def spy(self, *a, _verb=verb, _real=real, **kw):
            calls.append((_verb, kw))
            return _real(self, *a, **kw)
        mp.setattr(Porcelain, verb, spy)
    return calls


# ------------------------------------------------------------------ fault injection

class _Fault:
    """Fails the engine's atomic unit at the first op `match` selects. `mode="raise"`
    raises (AtomicAbort cause "exception"); `mode="skip"` gate-skips the row (cause
    "gate_skip"). Records whether it fired inside an OPEN unit and how many rows the
    unit had staged by then."""

    def __init__(self, match, mode="raise"):
        self.match, self.mode = match, mode
        self.fired = False
        self.in_unit = False
        self.ops_before = 0          # ops the unit applied before the fault
        self.staged_rows = None      # rows the unit had appended by then

    def install(self, mp):
        real_item, real_retract = Ingestor._ingest_item, TruthMaintenance.retract
        fault = self

        def _arm(buffer):
            fault.fired = True
            precall = buffer.unit_precall_head          # None outside an atomic unit
            fault.in_unit = precall is not None
            fault.staged_rows = buffer.head() - (precall or 0)

        def item(self, it, *a, **kw):  # the engine may pass more (pb batch B: call_frame)
            if not fault.fired and fault.match("assert", it):
                _arm(self._buffer)
                if fault.mode == "skip":
                    self._record_skip(it["entity"], it["attribute"], it.get("value"),
                                      "injected_skip")
                    return []
                raise RuntimeError("injected fault")
            if not fault.fired:
                fault.ops_before += 1
            return real_item(self, it, *a, **kw)

        def retract(self, target, reason):
            if not fault.fired and fault.match("retract", {"reason": reason}):
                _arm(self._buffer)
                raise RuntimeError("injected fault")
            if not fault.fired:
                fault.ops_before += 1
            return real_retract(self, target, reason)

        mp.setattr(Ingestor, "_ingest_item", item)
        mp.setattr(TruthMaintenance, "retract", retract)
        return self


def _nth_retract(n):
    seen = []

    def match(kind, _payload):
        if kind != "retract":
            return False
        seen.append(1)
        return len(seen) == n
    return match


def _row(entity=None, attribute=None, prefix=None, value_type=None):
    def match(kind, item):
        return (kind == "assert"
                and (entity is None or item.get("entity") == entity)
                and (prefix is None or str(item.get("entity", "")).startswith(prefix))
                and (attribute is None or item.get("attribute") == attribute)
                and (value_type is None or item.get("value_type") == value_type))
    return match


# Every write the continuation's set makes, in its op order.
CONTINUATION_FAULTS = {
    "settled_record": _row(prefix="settled:episode_"),
    "personal_threads": _row(entity="session:personal_threads"),
    "retract_manifest_1st": _nth_retract(1),
    "retract_manifest_2nd": _nth_retract(2),
    "new_arc_row": _row(prefix="arc:ep_", attribute="kind"),
    "new_beat_row": _row(prefix="beat:", attribute="achievable_via"),
    "arc_index": _row(prefix="arc:ep_", attribute="beat_index"),
    "manifest_arc_ids": _row(entity="arc:portfolio", attribute="arc_ids"),
    "manifest_main_arc": _row(entity="arc:portfolio", attribute="main_arc"),
    "episode_boundary": _row(prefix="event:episode_start_"),
    "doorway_time_jump": _row(entity="time:elapsed", value_type="delta"),
    "hook_cast_new_person": _row(entity=NEW_HOOK, attribute="kind"),
    "hook_cast_staging": _row(entity=OLD_HOOK, attribute="in"),
    "episode_entry_epoch": _row(entity="session:episode", attribute="entry_epoch"),
    "episode_scope": _row(entity="session:episode", attribute="arc_scope"),
    "independent_scope": _row(entity="session:scope", attribute="independent_extra"),
    "chapter_title": _row(entity="session:episode", attribute="chapter_title"),
    "chapter_death_policy": _row(entity="session:episode", attribute="death_policy"),
    "callback_receipt": _row(attribute="surfaced_turn"),     # the LAST op of the set
}


@pytest.mark.parametrize("point", list(CONTINUATION_FAULTS), ids=list(CONTINUATION_FAULTS))
def test_continuation_failure_at_any_write_leaves_the_slot_untouched(
        tmp_path, monkeypatch, point):
    name = _make_slot(tmp_path, monkeypatch)
    before = _snapshot(name)
    assert before["portfolio"] is not None and before["main_arc"] == "arc:main"
    epoch_before = executor.current_epoch()
    with pytest.MonkeyPatch.context() as mp:
        fault = _Fault(CONTINUATION_FAULTS[point]).install(mp)
        with pytest.raises(RuntimeError, match="nothing was written") as err:
            game.continue_episode(name, _Provider(), player_id="u1")
    # the fault fired INSIDE the engine's atomic unit, after the unit had staged rows
    assert fault.fired and fault.in_unit
    assert isinstance(err.value.__cause__, AtomicAbort)
    assert err.value.__cause__.cause == "exception"
    if point != "settled_record":                       # the first op stages nothing
        assert fault.ops_before > 0 and fault.staged_rows >= fault.ops_before
    assert executor.current_epoch() == epoch_before
    # the slot: same rows, same manifest assertion ids, same arc, same clock
    assert _snapshot(name) == before
    w = _open(game.slot_path(name, "u1"), name)
    try:
        ents = {str(r.entity) for r in w.buffer.visible()}
        assert not any(e.startswith(("settled:episode_", "event:episode_start_", "arc:ep_"))
                       for e in ents)
        assert not ({"session:personal_threads", "session:episode", NEW_HOOK} & ents)
        reads = PorcelainWorldReads(w)
        assert arc_io.arc_from_frame(reads, "arc:main").beats
        assert w.porcelain.state("arc:portfolio", "main_arc",
                                 frame=PLOT)["status"] == "known"     # not conflicted
    finally:
        w.close()


def test_continuation_gate_skip_aborts_the_whole_set(tmp_path, monkeypatch):
    """The other abort cause: a row the gate SKIPS (receipt-and-continue on the plain
    ingest path) aborts the atomic set as a whole, with nothing written."""
    name = _make_slot(tmp_path, monkeypatch)
    before = _snapshot(name)
    with pytest.MonkeyPatch.context() as mp:
        fault = _Fault(_row(entity="session:episode", attribute="chapter_title"),
                       mode="skip").install(mp)
        with pytest.raises(RuntimeError, match="nothing was written") as err:
            game.continue_episode(name, _Provider(), player_id="u1")
    assert fault.fired and fault.in_unit and fault.staged_rows > 0
    assert err.value.__cause__.cause == "gate_skip"
    assert _snapshot(name) == before


def test_retry_after_a_failed_continuation_writes_exactly_one_chapter(tmp_path, monkeypatch):
    """B5: a retry after a failure used to append duplicates (settled marks, the boundary)
    on top of a half-written chapter. Now the failed attempt left nothing, so the retry's
    chapter is the only one."""
    name = _make_slot(tmp_path, monkeypatch)
    with pytest.MonkeyPatch.context() as mp:
        _Fault(_row(entity="arc:portfolio", attribute="main_arc")).install(mp)
        with pytest.raises(RuntimeError):
            game.continue_episode(name, _Provider(), player_id="u1")
    meta = game.continue_episode(name, _Provider(), player_id="u1")
    after = _snapshot(name)
    assert after["main_arc"] == meta["main_arc"] and meta["main_arc"].startswith("arc:ep_")
    assert after["portfolio"].main_arc == meta["main_arc"]     # verified: one row per control
    assert after["minutes"] > 0                                 # the doorway's time jump landed
    w = _open(game.slot_path(name, "u1"), name)
    try:
        rows = [(str(r.entity), str(r.attribute)) for r in w.buffer.visible()]
        assert sum(e.startswith("settled:episode_") for e, _a in rows) == 1
        assert sum(e.startswith("event:episode_start_") for e, _a in rows) == 1
        assert w.porcelain.locate(NEW_HOOK)[0] == "place:roof"
        assert w.porcelain.locate(OLD_HOOK)[0] == "place:roof"
    finally:
        w.close()


def test_continuation_writes_through_one_commit_set_and_nothing_else(tmp_path, monkeypatch):
    """Compute everything, then commit once: no ingest or retract reaches the slot outside
    the single commit_set, and the set is model-free (classify="rules")."""
    name = _make_slot(tmp_path, monkeypatch)
    with pytest.MonkeyPatch.context() as mp:
        calls = _spy_writes(mp)
        meta = game.continue_episode(name, _Provider(), player_id="u1")
    assert [verb for verb, _kw in calls] == ["commit_set"]
    assert calls[0][1].get("classify") == "rules"
    after = _snapshot(name)
    assert after["portfolio"] is not None and after["portfolio"].main_arc == meta["main_arc"]
    assert set(after["arc_ids"]) == {"arc:main", meta["main_arc"]}


def test_continuation_drops_only_the_hook_rows_the_gate_would_skip(tmp_path, monkeypatch):
    """A malformed hook-cast id from the model used to be skipped row by row while the
    rest of the chapter landed. Inside one atomic set a skip would abort the chapter, so
    the planner drops exactly those rows first: the continuation still commits, and the
    well-formed hook person is staged."""
    name = _make_slot(tmp_path, monkeypatch)
    proposal = {**_PROPOSAL, "hook_cast": [{"id": "person:Mr Smith", "name": "Mr Smith"},
                                           {"id": NEW_HOOK, "name": "Wren Shaw"}]}
    meta = game.continue_episode(name, _Provider(proposal), player_id="u1")
    assert meta["main_arc"].startswith("arc:ep_")
    w = _open(game.slot_path(name, "u1"), name)
    try:
        assert w.porcelain.locate(NEW_HOOK)[0] == "place:roof"
        assert not any(str(r.entity) == "person:Mr Smith" for r in w.buffer.visible())
    finally:
        w.close()


# ------------------------------------------------------------------------- replan

def _replan_world(tmp_path, *, manifest="clean"):
    """A playing world with a sealed main arc. `manifest`: "clean" (one CONSTITUTIVE row
    per control attribute), "conflicted" (an older writer appended a second main_arc
    without retracting), or "absent" (a legacy single-arc world)."""
    path = tmp_path / "replan.world"
    w = _open(path, "replan")
    w.ingestor.cursor.advance(1.0)
    w.ingest_structured([
        {"entity": "place:study", "attribute": "kind", "value": "room", "timeless": True},
        {"entity": PLAYER, "attribute": "kind", "value": "person", "timeless": True},
    ])
    main = game._build_arc({**_PROPOSAL, "title": "First"}, arc_id="arc:main")
    w.porcelain.ingest_structured(arc_io.arc_to_items(main) + arc_io.index_items(main))
    if manifest != "absent":
        w.porcelain.ingest_structured(
            arc_io.portfolio_items(["arc:main"], main_arc_id="arc:main"), frame=PLOT)
    if manifest == "conflicted":
        w.porcelain.ingest_structured(
            arc_io.portfolio_items(["arc:main"], main_arc_id="arc:stale",
                                   valid_from=1003.0)[1:], frame=PLOT)
    return path, w


def _replacement(turn=8):
    return game._build_arc({**_PROPOSAL, "title": "Reshaped",
                            "beats": [{**_PROPOSAL["beats"][0], "id": "beat:who_tried"}]},
                           arc_id=f"arc:replan_{turn}")


REPLAN_FAULTS = {
    "retract_manifest_1st": _nth_retract(1),
    "retract_manifest_2nd": _nth_retract(2),
    "new_arc_row": _row(entity="arc:replan_8", attribute="kind"),
    "new_beat_row": _row(prefix="beat:who_tried", attribute="achievable_via"),
    "arc_index": _row(entity="arc:replan_8", attribute="beat_index"),
    "manifest_arc_ids": _row(entity="arc:portfolio", attribute="arc_ids"),
    "manifest_main_arc": _row(entity="arc:portfolio", attribute="main_arc"),   # the last op
}


@pytest.mark.parametrize("point", list(REPLAN_FAULTS), ids=list(REPLAN_FAULTS))
def test_replan_failure_midway_leaves_the_old_arc_and_manifest(tmp_path, point):
    path, w = _replan_world(tmp_path)
    state_before = read_portfolio_state(PorcelainWorldReads(w))
    head_before = w.buffer.head()
    assert state_before is not None and state_before.main_arc == "arc:main"
    with pytest.MonkeyPatch.context() as mp:
        fault = _Fault(REPLAN_FAULTS[point]).install(mp)
        with pytest.raises(RuntimeError, match="nothing was written"):
            arc_io.replan_main_arc(w, _replacement(), turn=8)
    assert fault.fired and fault.in_unit
    if point != "retract_manifest_1st":                 # the first op stages nothing
        assert fault.ops_before > 0 and fault.staged_rows >= fault.ops_before

    def intact(handle):
        reads = PorcelainWorldReads(handle)
        assert handle.buffer.head() == head_before
        assert read_portfolio_state(reads) == state_before        # the same manifest rows
        assert arc_io.main_arc_from_frame(reads) == "arc:main"
        assert arc_io.arc_ids_from_frame(reads) == ["arc:main"]
        assert reads.state("arc:replan_8", "kind", frame=PLOT) is None   # no half arc
        assert arc_io.arc_from_frame(reads, "arc:main").beats

    intact(w)                 # the SAME live handle the turn loop keeps using...
    w.close()
    w = _open(path, "replan")
    try:
        intact(w)             # ...and a fresh reopen
    finally:
        w.close()


def test_replan_success_is_one_verified_manifest_after_reopen(tmp_path):
    path, w = _replan_world(tmp_path)
    with pytest.MonkeyPatch.context() as mp:
        calls = _spy_writes(mp)
        assert arc_io.replan_main_arc(w, _replacement(), turn=8) == "arc:replan_8"
    assert [verb for verb, _kw in calls] == ["commit_set"]
    w.close()
    w = _open(path, "replan")
    try:
        reads = PorcelainWorldReads(w)
        state = read_portfolio_state(reads)
        assert state is not None                                # exactly one row per control
        assert state.main_arc == "arc:replan_8"
        assert state.arc_ids == ("arc:main", "arc:replan_8")
        assert arc_io.arc_from_frame(reads, "arc:replan_8").beats
    finally:
        w.close()


@pytest.mark.parametrize("manifest", ["conflicted", "absent"])
def test_replan_repairs_a_conflicted_manifest_and_seeds_an_absent_one(tmp_path, manifest):
    """Why the swaps do not gate on tangent's PortfolioState: it fails closed on these two
    states, and a swap must still happen. A conflicted manifest is repaired (every visible
    control row retracted in the set); a legacy world without one gets a fresh one."""
    path, w = _replan_world(tmp_path, manifest=manifest)
    assert read_portfolio_state(PorcelainWorldReads(w)) is None
    arc_io.replan_main_arc(w, _replacement(), turn=8)
    w.close()
    w = _open(path, "replan")
    try:
        state = read_portfolio_state(PorcelainWorldReads(w))
        assert state is not None and state.main_arc == "arc:replan_8"
        assert w.porcelain.state("arc:portfolio", "main_arc",
                                 frame=PLOT)["status"] == "known"
    finally:
        w.close()


def test_replan_refuses_an_engine_without_commit_set(tmp_path):
    """No atomic door: refused before writing (a non-atomic swap can leave no manifest)."""
    path, w = _replan_world(tmp_path)

    class _NoDoor:
        def __init__(self, p):
            self._p = p

        def __getattr__(self, attr):
            if attr == "commit_set":
                raise AttributeError(attr)
            return getattr(self._p, attr)

    class _View:
        porcelain = _NoDoor(w.porcelain)

    head = w.buffer.head()
    try:
        with pytest.raises(RuntimeError, match="no commit_set"):
            arc_io.replan_main_arc(_View(), _replacement(), turn=8)
        assert w.buffer.head() == head
        assert arc_io.main_arc_from_frame(PorcelainWorldReads(w)) == "arc:main"
    finally:
        w.close()
