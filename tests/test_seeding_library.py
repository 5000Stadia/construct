"""SEEDING-LIBRARY-WIRING r2.1 (cr GREEN): registry-first seeding through pattern-buffer's build
library (BUILD-LIBRARY-V1 r1.8.3, identity_time='gate').

The planted-trap story (r4's traps): Rex the man and Rex the dog; two Brecks and an ambiguous
"Breck"; "the stranger" introduced in chapter 2 and revealed in chapter 3 as Duke Orrin, an
entry first appearing in chapter 3; and Mara's guise, "the masked rower", first introduced in
chapter 3. The extractor is a stub that writes the library's line grammar against the
prompt's numbered passage; the world, the library and every read are real."""

import json
import re

import pytest

from construct import game, seeding
from construct.adapter import HorizonView, PorcelainWorldReads
from construct.arc.executor import ENTRY_MARGIN, SOURCE_STEP
from tests.test_integration import rule_classifier_fallback

pytestmark = pytest.mark.usefixtures("_library_on")

OPENING = SOURCE_STEP + ENTRY_MARGIN

STORY = """# The Ferry

## One

Rex Hall kept the ferry at Low Crossing. His old dog Rex slept by the stove. Tomas Breck and Ada Breck ran the toll house. Breck counted the tolls.

## Two

The stranger watched from the bank. Rex barked at the water.

## Three

Duke Orrin came down the river at last. The stranger was Duke Orrin all along. A masked rower took the ferry out. The masked rower was Mara Venn. Mara Venn had mended nets at Low Crossing.
"""

MANIFEST = {
    "entries": [
        {"key": "rex_man", "type": "person", "names": ["Rex", "Rex Hall"],
         "anchor_quote": "Rex Hall kept the ferry at Low Crossing.", "role": "ferryman"},
        {"key": "rex_dog", "type": "animal", "species": "dog", "names": ["Rex"],
         "anchor_quote": "His old dog Rex slept by the stove."},
        {"key": "tomas", "type": "person", "names": ["Tomas Breck", "Breck"],
         "anchor_quote": "Tomas Breck and Ada Breck ran the toll house."},
        {"key": "ada", "type": "person", "names": ["Ada Breck", "Breck"],
         "anchor_quote": "Tomas Breck and Ada Breck ran the toll house."},
        {"key": "crossing", "type": "place", "names": ["Low Crossing"],
         "anchor_quote": "Rex Hall kept the ferry at Low Crossing."},
        {"key": "duke", "type": "person", "names": ["Duke Orrin"],
         "anchor_quote": "Duke Orrin came down the river at last.",
         "personas": [{"name": "the stranger",
                       "intro_quote": "The stranger watched from the bank.",
                       "reveal_quote": "The stranger was Duke Orrin all along."}]},
        {"key": "mara", "type": "person", "names": ["Mara Venn"],
         "anchor_quote": "Mara Venn had mended nets at Low Crossing.",
         "personas": [{"name": "the masked rower",
                       "intro_quote": "A masked rower took the ferry out.",
                       "reveal_quote": "The masked rower was Mara Venn."}]},
    ],
    "namesakes": [],
}


@pytest.fixture
def _library_on(monkeypatch):
    monkeypatch.setenv(seeding.LIBRARY_ENV, "1")


def _sentence(prompt: str, words: str) -> int:
    for m in re.finditer(r"\[s(\d+)\]\s*([^\n]*)", prompt):
        if words in m.group(2):
            return int(m.group(1))
    raise AssertionError(f"no sentence with {words!r} in the passage")


def _cands(prompt: str) -> dict[str, str]:
    """{name: id} from the prompt's CANDIDATES table (id | type | names | gate)."""
    out: dict[str, str] = {}
    block = prompt.split("CANDIDATES", 1)[1].split("PASSAGE", 1)[0]
    for line in block.splitlines():
        parts = [p.strip() for p in line.split("|")]
        if len(parts) == 4 and ":" in parts[0]:
            for name in parts[2].split(";"):
                out.setdefault(name.strip(), parts[0])
    return out


class Extractor:
    """The library's model: scripted grammar lines per chapter; counts its calls."""

    def __init__(self, schedule: dict | None = None, unused_handle_chunk: int | None = None):
        """`schedule`: {chunk index: ["raise" | "refuse", ...]}, consumed one per call to
        that chunk; then the chunk answers normally. "refuse" returns an answer the library
        refuses whole (a line using an undeclared handle). `unused_handle_chunk` declares an
        escape no line uses (r1.9.1 drops it with a receipt)."""
        self.calls: list[int] = []
        self.schedule = {k: list(v) for k, v in (schedule or {}).items()}
        self.unused_handle_chunk = unused_handle_chunk
        self.classify = rule_classifier_fallback()

    def __call__(self, prompt: str, schema: dict):
        if prompt.startswith("Classify the lifetime"):
            return self.classify(prompt, schema)
        assert prompt.startswith("Extract world-state facts (build library"), prompt[:60]
        chunk = int(re.search(r"PASSAGE \(chunk (\d+), chapter \d+\)", prompt).group(1))
        self.calls.append(chunk)
        plan = self.schedule.get(chunk) or []
        if plan:
            action = plan.pop(0)
            n = self.calls.count(chunk)               # 1st, 2nd... call to this chunk
            if action == "raise":
                raise RuntimeError(f"model call failed #{n}")
            return {"lines": [f"s{_first_sentence(prompt)}|new:{10 + n}|role|nobody"]}
        c = _cands(prompt)
        lines, picks = [], []

        def at(words, build):
            try:
                n = _sentence(prompt, words)
            except AssertionError:
                return                       # that sentence is in another chunk
            lines.append(f"s{n}|" + build())
        at("Rex Hall kept", lambda: f"{c['Rex Hall']}|in|@{c['Low Crossing']}")
        at("His old dog", lambda: f"{_dog(prompt)}|in|@{c['Low Crossing']}")
        at("His old dog", lambda: f"{_dog(prompt)}|posture|sleeping")
        at("Breck counted", lambda: "new:0|role|toll counter")
        if any(line.split("|")[1] == "new:0" for line in lines):
            picks.append({"handle": "new:0", "surface": "Breck",
                          "candidates": [c["Tomas Breck"], c["Ada Breck"]],
                          "choice": c["Tomas Breck"], "evidence_quote": "Breck counted the tolls."})
        at("The stranger watched", lambda: f"{c['the stranger']}|in|@{c['Low Crossing']}")
        at("Duke Orrin came", lambda: f"{c['Duke Orrin']}|role|duke")
        at("Mara Venn had", lambda: f"{c['Mara Venn']}|in|@{c['Low Crossing']}")
        escapes = []
        if chunk == self.unused_handle_chunk:
            escapes.append({"handle": "new:7", "type": "object", "name": "a stray oar",
                            "species": None, "quote": "the ferry"})
        return {"lines": lines, "picks": picks, "escapes": escapes}


def _first_sentence(prompt: str) -> int:
    return int(re.search(r"\[s(\d+)\]", prompt).group(1))


def _dog(prompt: str) -> str:
    for line in prompt.splitlines():
        if "| animal, dog |" in line:
            return line.split("|")[0].strip()
    raise AssertionError("no dog candidate")


class Repairs:
    def __init__(self, answer=None):
        self.calls: list[list] = []
        self.answer = answer

    def __call__(self, prose, manifest, problems):
        self.calls.append(problems)
        return self.answer


def _play_model():
    """The world's engine model in play: the rule classifier, and empty extractions."""
    from patternbuffer.testing import StubModel
    rule = rule_classifier_fallback()
    return StubModel(fallback=lambda prompt, schema: rule(prompt, schema)
                     if prompt.startswith("Classify the lifetime") else {"items": []})


def _build(tmp_path, manifest=MANIFEST, extractor=None, repair=None, monkeypatch=None,
           model=None):
    w = game._world(tmp_path / "s.world", "s", model=model)
    w.porcelain.begin_build()
    stages: list[str] = []
    registry = seeding.ingest_library(
        w, game._chunk_chapters(STORY), STORY, manifest,
        model=extractor or Extractor(), repair=repair or Repairs(),
        source_step=SOURCE_STEP, on_stage=stages.append)
    game._hold_manifest_namesakes_apart(w, registry)
    entries = registry.entries()
    w.porcelain.seal_build(model=False)
    return w, entries, stages


def _ids(entries, key):
    return next(e["id"] for e in entries if e["key"] == key)


# ---------------------------------------------------------------- 1. the manifest round trip

def test_the_manifest_mints_ids_by_code(tmp_path):
    w, entries, _ = _build(tmp_path)
    try:
        assert _ids(entries, "rex_man") == "person:rex"
        assert _ids(entries, "rex_dog") == "person:rex_2"
        p = w.porcelain
        assert p.state("person:rex", "kind")["fact"]["value"] == "person"
        assert p.state("person:rex_2", "being_type")["fact"]["value"] == "animal"
        assert p.state("person:rex_2", "species")["fact"]["value"] == "dog"
    finally:
        w.close()


def test_the_author_schema_carries_the_manifest_and_it_is_saved_beside_the_prose(
        tmp_path, monkeypatch):
    from construct import cohorts
    assert "manifest" in cohorts.STORY_AUTHOR_SCHEMA["required"]
    monkeypatch.setattr(game, "GENERATED_DIR", tmp_path)
    raw = {"entries": MANIFEST["entries"],
           "namesakes": [{"a": "rex_man", "b": "rex_dog",
                          "anchor_quote": "His old dog Rex slept by the stove."}]}
    path = game._save_generated_prose("ferry", {"title": "The Ferry", "prose": STORY,
                                                "manifest": raw})
    saved = json.loads(seeding.manifest_path(path).read_text())
    assert saved["namesakes"] == [["rex_man", "rex_dog", "His old dog Rex slept by the stove."]]
    assert seeding.load_manifest(path) == saved


# ---------------------------------------------------------------- 2. repair, then fallback

def _bad_manifest():
    bad = json.loads(json.dumps(MANIFEST))
    bad["entries"][0]["anchor_quote"] = "A sentence the prose never wrote."
    return bad


def test_a_bad_manifest_gets_one_repair_with_the_problem_list(tmp_path):
    repair = Repairs(answer=MANIFEST)
    w, entries, stages = _build(tmp_path, manifest=_bad_manifest(), repair=repair)
    try:
        assert len(repair.calls) == 1
        assert any(p["code"] == "quote_not_found" for p in repair.calls[0])
        assert _ids(entries, "rex_man") == "person:rex"
        assert any("one repair" in m for m in stages)
    finally:
        w.close()


def test_a_second_bad_manifest_falls_back_to_the_category_passes(tmp_path, monkeypatch,
                                                                    caplog):
    from patternbuffer.build import Manifest
    called = []

    def passes(texts, model):
        called.append(sorted(texts))
        return Manifest.from_dict(MANIFEST)
    monkeypatch.setattr("patternbuffer.build.category_passes", passes)
    repair = Repairs(answer=_bad_manifest())
    with caplog.at_level("WARNING"):
        w, entries, _ = _build(tmp_path, manifest=_bad_manifest(), repair=repair)
    try:
        assert len(repair.calls) == 1 and called
        assert "manifest_fallback" in caplog.text
    finally:
        w.close()


def test_imported_prose_takes_the_category_passes_directly(tmp_path, monkeypatch):
    from patternbuffer.build import Manifest
    monkeypatch.setattr("patternbuffer.build.category_passes",
                        lambda texts, model: Manifest.from_dict(MANIFEST))
    repair = Repairs()
    w, entries, _ = _build(tmp_path, manifest=None, repair=repair)
    try:
        assert repair.calls == [] and _ids(entries, "rex_dog") == "person:rex_2"
    finally:
        w.close()


# ---------------------------------------------------------------- 3. Rex, and 7: held apart

def test_rex_the_man_and_rex_the_dog_stay_two_and_are_held_apart(tmp_path):
    w, _, _ = _build(tmp_path)
    try:
        p = w.porcelain
        assert set(p.closure("person:rex")) == {"person:rex"}
        assert p.distinct_between("person:rex", "person:rex_2")
        assert p.state("person:rex_2", "posture", as_of=OPENING)["fact"]["value"] == "sleeping"
        people = game._known_people(HorizonView(w, OPENING))
        assert "person:rex" in people and "person:rex_2" in people
        assert "person:rex_2" in game._world_digest(HorizonView(w, OPENING))
    finally:
        w.close()


# ---------------------------------------------------------------- 4. two Brecks, and 8b

def test_an_ambiguous_breck_lands_on_a_provisional_id_out_of_play(tmp_path):
    w, entries, _ = _build(tmp_path)
    try:
        p = w.porcelain
        mentions = [e for e in p.entities("canon") if seeding.is_mention(e)]
        assert len(mentions) == 1
        assert p.state(mentions[0], "role")["fact"]["value"] == "toll counter"
        for breck in (_ids(entries, "tomas"), _ids(entries, "ada")):
            assert p.state(breck, "role")["status"] == "unknown"   # no fact on either Breck
        assert not set(mentions) & game._canon_entity_ids(w)
        assert not p.distinct_between(mentions[0], _ids(entries, "tomas"))
        load_bearing = {_ids(entries, "tomas"), "person:rex"}
        stops = game._identity_stops(w, load_bearing)
        assert not [s for s in stops if seeding.is_mention(s[0]) or seeding.is_mention(s[1])]
        assert not [s for s in game._role_kind_pairs(w)
                    if seeding.is_mention(s[0]) or seeding.is_mention(s[1])]
    finally:
        w.close()


def test_a_manifest_same_name_pair_touching_the_hero_still_stops(tmp_path):
    # 8b's negative control: the mention exception is for provisional ids only. An unheld
    # manifest-to-manifest same-name pair touching a load-bearing closure stops as today.
    w, entries, _ = _build(tmp_path)
    try:
        p = w.porcelain
        tomas, ada = _ids(entries, "tomas"), _ids(entries, "ada")
        assert p.distinct_between(tomas, ada)                     # rule 7 held them apart
        groups = [{"anchor": "breck", "live": True, "entities": [tomas, ada],
                   "kinds": ["person", "person"],
                   "pairs": [{"a": tomas, "b": ada, "status": "auto_declined",
                              "reason": "alias_not_specific"}]}]
        audit = {"name_collisions": groups}
        real = p.fidelity_audit
        p.fidelity_audit = lambda *a, **k: audit
        p.distinct_between = lambda a, b: []                      # as if never held apart
        try:
            assert game._identity_stops(w, {tomas})
        finally:
            p.fidelity_audit = real
    finally:
        w.close()


# ---------------------------------------------------------------- 5. late reveal, late entry

def test_nothing_from_chapter_three_is_visible_at_the_opening(tmp_path):
    w, entries, _ = _build(tmp_path)
    try:
        p = w.porcelain
        duke = _ids(entries, "duke")
        stranger = next(q["id"] for e in entries if e["key"] == "duke" for q in e["personas"])
        rower = next(q["id"] for e in entries if e["key"] == "mara" for q in e["personas"])
        at_open = set(p.entities("canon", as_of=OPENING))
        for late in (duke, stranger, rower):
            assert late not in at_open
            assert p.state(late, "kind", as_of=OPENING)["status"] == "unknown"
            assert p.state(late, "name", as_of=OPENING)["status"] == "unknown"
        view = HorizonView(w, OPENING)
        ids = game._canon_entity_ids(view)
        assert not {duke, stranger, rower} & ids
        digest = game._world_digest(view)
        assert "Orrin" not in digest and "stranger" not in digest and "masked" not in digest
        # negative control: at the head, all of them are present
        head = set(p.entities("canon"))
        assert {duke, stranger, rower} <= head
        assert PorcelainWorldReads(w).has_entity(duke)
    finally:
        w.close()


# ---------------------------------------------------------------- 6. the time mapping

def test_chapter_times_sit_on_the_source_axis():
    from types import SimpleNamespace as C
    chunks = [C(index=0, chapter=1), C(index=1, chapter=2), C(index=2, chapter=2),
              C(index=3, chapter=3)]
    t = seeding.chunk_times(chunks, SOURCE_STEP)
    assert t[0] == SOURCE_STEP and t[0] < OPENING
    assert t[1] == 2 * SOURCE_STEP and t[2] == 2 * SOURCE_STEP + 1     # split chapter: distinct
    assert t[3] == 3 * SOURCE_STEP


def test_chapter_one_facts_sit_below_the_opening(tmp_path):
    w, _, _ = _build(tmp_path)
    try:
        st = w.porcelain.state("person:rex", "in", as_of=OPENING)
        assert st["status"] == "known" and st["fact"]["valid"][0] < OPENING
    finally:
        w.close()


# ---------------------------------------------------------------- 7. chunk errors (r2.2)

def _try_build(tmp_path, ex):
    w = game._world(tmp_path / "s.world", "s", model=None)
    w.porcelain.begin_build()
    before = len(w.porcelain.facts("canon"))
    try:
        seeding.ingest_library(w, game._chunk_chapters(STORY), STORY, MANIFEST, model=ex,
                               repair=Repairs(), source_step=SOURCE_STEP,
                               on_stage=lambda m: None)
        return w, before, None
    except RuntimeError as exc:
        return w, before, exc


def test_refuse_then_accept_is_the_library_retry_and_builds(tmp_path):
    ex = Extractor(schedule={1: ["refuse"]})
    w, _, err = _try_build(tmp_path, ex)
    try:
        assert err is None and ex.calls.count(1) == 2 and ex.calls.count(0) == 1
    finally:
        w.close()


def test_raise_then_accept_is_construct_s_rerun_and_builds(tmp_path):
    ex = Extractor(schedule={1: ["raise"]})
    w, _, err = _try_build(tmp_path, ex)
    try:
        assert err is None and ex.calls.count(1) == 2
    finally:
        w.close()


def test_raise_then_refuse_stops_after_exactly_two_calls(tmp_path):
    ex = Extractor(schedule={1: ["raise", "refuse", "refuse"]})
    w, before, err = _try_build(tmp_path, ex)
    try:
        assert err is not None and "chunk 1 refused" in str(err)
        assert "model call failed #1" in str(err)             # the original exception
        assert "new:12" not in str(err)                       # not the re-run's refusal
        assert ex.calls.count(1) == 2                         # no third call
        assert len(w.porcelain.facts("canon")) == before      # nothing committed
    finally:
        w.close()


def test_refuse_then_refuse_stops_without_a_construct_rerun(tmp_path):
    ex = Extractor(schedule={1: ["refuse", "refuse", "refuse"]})
    w, before, err = _try_build(tmp_path, ex)
    try:
        assert err is not None and ex.calls.count(1) == 2
        assert "new:11" in str(err) and "new:12" not in str(err)   # the FIRST refusal
        assert len(w.porcelain.facts("canon")) == before
    finally:
        w.close()


def test_raise_then_raise_stops_after_two_calls(tmp_path):
    ex = Extractor(schedule={1: ["raise", "raise", "raise"]})
    w, before, err = _try_build(tmp_path, ex)
    try:
        assert err is not None and ex.calls.count(1) == 2
        assert "model call failed #1" in str(err) and "#2" not in str(err)   # the FIRST
        assert len(w.porcelain.facts("canon")) == before
    finally:
        w.close()


def test_an_unused_handle_is_dropped_logged_and_the_build_completes(tmp_path, caplog):
    ex = Extractor(unused_handle_chunk=0)
    stages = []
    w = game._world(tmp_path / "s.world", "s", model=None)
    try:
        w.porcelain.begin_build()
        with caplog.at_level("INFO"):
            seeding.ingest_library(w, game._chunk_chapters(STORY), STORY, MANIFEST,
                                   model=ex, repair=Repairs(), source_step=SOURCE_STEP,
                                   on_stage=stages.append)
        assert "dropped handle" in caplog.text and "a stray oar" in caplog.text
        assert any("1 dropped handle(s)" in m for m in stages)
        assert ex.calls.count(0) == 1                         # no retry for a drop
    finally:
        w.close()


# ---------------------------------------------------------------- 8. stage 2 off, stage 3 on

def test_library_mode_skips_stage_two_and_keeps_stage_three(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(game, "_stage_reconcile_identity",
                        lambda *a, **k: calls.append("stage2"))
    declared = []
    real_policy = game._stage_declare_policy
    monkeypatch.setattr(game, "_stage_declare_policy",
                        lambda world, on_stage: (declared.append(1), real_policy(world, on_stage)))

    class Stop(Exception):
        pass

    def stop(*a, **k):
        raise Stop
    monkeypatch.setattr(game, "_stage_establish_epoch", stop)
    w, entries, _ = _build(tmp_path)
    stages = []
    try:
        with pytest.raises(Stop):
            game._finalize_scenario_impl(w, "s", "S", None, tmp_path / "s.world", False,
                                         on_stage=stages.append, library_entries=entries)
        assert calls == [] and declared == [1]
        assert any("identity decided by the manifest (library)" in m for m in stages)
        assert w.porcelain.facts("canon", prefix="traversal:")
        mentions = [e for e in w.porcelain.entities("canon") if seeding.is_mention(e)]
        assert mentions and not w.porcelain.facts("canon", entity=mentions[0],
                                                  attribute="distinct_from")
    finally:
        w.close()


# ---------------------------------------------------------------- 9. the switch

def test_the_switch_selects_the_per_chunk_path(monkeypatch):
    monkeypatch.setenv(seeding.LIBRARY_ENV, "0")
    assert not seeding.library_enabled()
    monkeypatch.setenv(seeding.LIBRARY_ENV, "1")
    assert seeding.library_enabled()


def test_the_ingest_path_routes_by_the_switch(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "worlds").mkdir()
    prose = tmp_path / "ferry.md"
    prose.write_text(STORY)
    seeding.manifest_path(prose).write_text(json.dumps(MANIFEST))
    seen = {}

    def fake_library(world, chunks, text, manifest, **kw):
        seen["manifest"] = manifest
        from types import SimpleNamespace
        return SimpleNamespace(entries=lambda: [{"id": "person:rex"}], identities=(),
                               namesakes=())

    def fake_finalize(*a, **kw):
        seen["entries"] = kw.get("library_entries")
        return {}
    monkeypatch.setattr(seeding, "ingest_library", fake_library)
    monkeypatch.setattr(game, "_finalize_scenario", fake_finalize)
    game.create_scenario_from_ingest("ferry", prose, provider=None)
    assert seen["manifest"]["entries"][0]["key"] == "rex_man"
    assert seen["entries"] == [{"id": "person:rex"}]


# ---------------------------------------------------------------- routing and the cast note

def test_category_and_extract_heads_route_to_the_cheap_tier():
    from patternbuffer.build import CATEGORY_HEAD, EXTRACT_HEAD

    from construct.provider import _CHEAP_ENGINE_PREFIXES
    assert EXTRACT_HEAD.startswith(_CHEAP_ENGINE_PREFIXES)
    assert CATEGORY_HEAD.format(category="beings").startswith(_CHEAP_ENGINE_PREFIXES)


def test_the_cast_note_lists_beings_with_names_type_and_role(tmp_path):
    w, entries, _ = _build(tmp_path)
    try:
        note = seeding.cast_note(entries)
        assert "person:rex: Rex; Rex Hall (person; ferryman)" in note
        assert "person:rex_2: Rex (animal, dog)" in note
        assert "place:" not in note
    finally:
        w.close()


# ------------------------------------------- the play path on a library-built world (cr)

def _play(tmp_path, horizon, extra_scope=()):
    """A library-built world, then one real turn at `horizon` through a HorizonView, as
    Session plays it. The player stands at Low Crossing from below the opening."""
    from construct.turnloop import run_turn as _run
    from tests.test_integration import PLAYER, make_arc, seed_arc
    from tests.test_placements_by_rule import StubProvider
    w, entries, _ = _build(tmp_path, model=_play_model())
    crossing = _ids(entries, "crossing")
    w.porcelain.ingest_structured([
        {"entity": PLAYER, "attribute": "kind", "value": "person", "timeless": True},
        {"entity": PLAYER, "attribute": "in", "value": crossing, "value_type": "entity",
         "valid_from": SOURCE_STEP + 1}], frame="canon", classify="rules")
    # The player's frame holds every canon fact about the cast and places, each at its own
    # canon time (standing in for the build's knowledge seeding, which this harness skips):
    # the SCENE block reads that frame, so what reaches the narrator is decided by the
    # horizon alone.
    known = []
    for f in w.porcelain.facts("canon"):
        if (str(f["entity"]).startswith(("person:", "place:")) and f["entity"] != PLAYER
                and f["attribute"] in ("kind", "name", "in", "posture", "role", "species")):
            row = {"entity": f["entity"], "attribute": f["attribute"], "value": f["value"],
                   "value_type": f.get("value_type") or "literal"}
            vf = (f.get("valid") or [None])[0]
            row.update({"valid_from": vf} if vf is not None else {"timeless": True})
            known.append(row)
    w.porcelain.ingest_structured(known, frame=f"knows:{PLAYER}", classify="rules")
    arc = make_arc()
    seed_arc(w, arc)
    prov = StubProvider([{"kind": "action", "claims_are": "act", "moves_to": "",
                          "requires": [], "needs_test": False, "uncertain_of": "",
                          "commits": False, "commitment": ""},
                         {"prose": "The river runs grey past the crossing."}])
    r = _run(HorizonView(w, horizon), arc, prov, "I look around the crossing.", turn=1,
             scope=[PLAYER, crossing, *extra_scope], horizon=horizon)
    if getattr(r, "settle", None) is not None:
        r.settle()
    narrate = [c[0] for c in prov.calls if "THE SCENE RIGHT NOW" in c[0]]
    return w, entries, (narrate[-1] if narrate else r.trace.briefing)


def _block(brief: str, head: str) -> str:
    """One briefing block: from its heading to the next blank line."""
    return brief.split(head, 1)[1].split("\n\n", 1)[0]


CAST = ("person:rex", "person:rex_2")


def test_a_played_opening_scene_shows_rex_the_dog_and_his_fact(tmp_path):
    # the production briefing at the opening: the SCENE block carries the dog's fact, and
    # PRESENT CHARACTERS lists both Rexes (man and dog) at the crossing
    w, entries, brief = _play(tmp_path, OPENING + 1, extra_scope=CAST)
    try:
        scene = _block(brief, "THE SCENE RIGHT NOW")
        assert "sleeping" in scene and "Rex" in scene
        assert _block(brief, "PRESENT CHARACTERS").count("Rex: present") == 2
    finally:
        w.close()


def test_a_played_opening_reads_nothing_from_chapter_three(tmp_path):
    late = ("person:duke_orrin", "person:mara_venn")
    w, entries, brief = _play(tmp_path, OPENING + 1, extra_scope=CAST + late)
    try:
        for name in ("Duke Orrin", "Orrin", "stranger", "masked rower", "Mara Venn"):
            assert name not in brief, name
    finally:
        w.close()


def test_the_same_turn_at_a_late_horizon_does_read_chapter_three(tmp_path):
    # the negative control: past chapter 3's coordinates, the same play path's SCENE block
    # and PRESENT CHARACTERS show what the opening hid
    late = ("person:duke_orrin", "person:mara_venn")
    w, entries, brief = _play(tmp_path, 5 * SOURCE_STEP, extra_scope=CAST + late)
    try:
        assert "Mara Venn" in _block(brief, "PRESENT CHARACTERS")
        assert "Mara Venn" in _block(brief, "THE SCENE RIGHT NOW")
    finally:
        w.close()
