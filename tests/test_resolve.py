"""Entity Authority resolver (construct/resolve.py) — the pure decision layer that makes the
misshapen object graph impossible to create. Covers Cx 304's required regression pins at the
resolver level (the wiring-level pins — arc-key quarantine, terminal-no-canon — are covered in the
turn-loop integration tests once the sites are wired)."""
from __future__ import annotations

from construct import resolve


def _name_of(names):
    return lambda e: names.get(e, "")


# ---- predicates (absorbed the turnloop predicate coverage when the promote-gate copies were
#      stripped — verified-then-strip, Cx 313) -----------------------------------------------
def test_predicates():
    # malformed: stray-slash / empty local-part
    assert resolve.is_malformed("person:/you")
    assert resolve.is_malformed("place:/coffee_house")
    assert resolve.is_malformed("obj:/door_to_street")
    assert resolve.is_malformed("place:/")
    assert not resolve.is_malformed("obj:pencil")
    assert not resolve.is_malformed("person:clara_vale")
    assert not resolve.is_malformed("obj:brass_sample_token")
    assert not resolve.is_malformed("you")                # bare token, not an id
    assert not resolve.is_malformed(None)
    assert not resolve.is_malformed(123)
    # voice: narration-voice phantoms (whole-token)
    assert resolve.is_voice("person:narrator")
    assert resolve.is_voice("person:unknown_narrator")
    assert resolve.is_voice("person:unknown_speaker")
    assert resolve.is_voice("narrator")
    assert not resolve.is_voice("person:unknown_man")     # legit unidentified suspect
    assert not resolve.is_voice("person:speakman")        # whole-token, not substring
    assert not resolve.is_voice("person:clara_vale")
    assert not resolve.is_voice(None)
    # deixis: first/second-person → protagonist
    assert resolve.is_deixis("you") and resolve.is_deixis("person:you") and resolve.is_deixis("me")
    assert resolve.is_deixis("myself")
    assert not resolve.is_deixis("person:clara_vale")


# ---- Pin: 'plain pencil' binds to the scene obj:pencil, no obj:plain_pencil ------
def test_fragment_mention_binds_not_mints():
    names = {"obj:pencil": "pencil"}
    rows = [{"entity": "obj:plain_pencil", "attribute": "kind", "value": "pencil"},
            {"entity": "obj:plain_pencil", "attribute": "in", "value": "person:clara",
             "value_type": "entity"}]
    out, _ = resolve.resolve_rows(rows, scene={"obj:pencil", "person:clara"},
                                  protagonist="person:clara", name_of=_name_of(names))
    ids = {r["entity"] for r in out}
    assert ids == {"obj:pencil"}                 # bound to the existing pencil
    assert "obj:plain_pencil" not in ids         # no third sibling minted


# ---- Pin: take binds the same passively-introduced mug; zero-candidate mints -----
def test_bind_or_mint_take_binds_known_else_mints():
    names = {"obj:mug": "mug"}
    assert resolve.bind_or_mint("the mug", kind="obj", candidates={"obj:mug"},
                                protagonist="person:p", name_of=_name_of(names)) == ("obj:mug", "bound")
    assert resolve.bind_or_mint("a mug", kind="obj", candidates=set(),
                                protagonist="person:p", name_of=_name_of({})) == (None, "mint")


# ---- Pin: move vs take channel — place vs obj, never bind a mistyped twin --------
def test_channel_typing_move_wants_place_not_obj_twin():
    names = {"place:street": "street", "obj:street": "street"}
    # a MOVE binds the place, never the mistyped obj twin
    assert resolve.bind_or_mint("the street", kind="place", candidates={"place:street"},
                                protagonist="person:p", name_of=_name_of(names)) == ("place:street", "bound")
    # if only the mistyped obj:street exists, the move does NOT bind it → signals a place mint
    assert resolve.bind_or_mint("the street", kind="place", candidates={"obj:street"},
                                protagonist="person:p", name_of=_name_of(names)) == (None, "mint")


# ---- Pin: entity-valued repair/drop — phantoms/desync never reach canon ----------
def test_entity_valued_phantoms_and_desync_dropped():
    names = {}
    rows = [
        {"entity": "obj:pencil", "attribute": "in", "value": "person:unknown_speaker", "value_type": "entity"},
        {"entity": "person:/you", "attribute": "in", "value": "place:/coffee_house", "value_type": "entity"},
        {"entity": "person:you", "attribute": "in", "value": "obj:street", "value_type": "entity"},
    ]
    out, receipts = resolve.resolve_rows(rows, scene={"obj:pencil"}, protagonist="person:clara",
                                         name_of=_name_of(names))
    # NONE of the three reach canon
    assert out == []
    reasons = {r[2] for r in receipts}
    assert "dropped_voice" in reasons          # unknown_speaker value
    assert "dropped_malformed" in reasons      # person:/you / place:/coffee_house
    # the person-in-obj:street row drops on a typing guard (obj:street is place-like → denied)
    assert reasons & {"kind_mismatch", "place_like_obj_denied"}


def test_person_in_real_object_is_kind_mismatch_dropped():
    # the kind expectation proper: a person located in a REAL (non-place-like) present object is a
    # desync and drops on kind_mismatch (person.in must be a place/person, never an object).
    names = {"obj:chair": "chair"}
    rows = [{"entity": "person:you", "attribute": "in", "value": "obj:chair", "value_type": "entity"}]
    out, receipts = resolve.resolve_rows(rows, scene={"obj:chair"}, protagonist="person:clara",
                                         name_of=_name_of(names))
    assert out == []
    assert any(r[2] == "kind_mismatch" for r in receipts)


def test_deixis_value_binds_to_protagonist():
    # a HELD relation onto 'you' → the protagonist (not a phantom holder)
    rows = [{"entity": "obj:lamp", "attribute": "in", "value": "person:you", "value_type": "entity"}]
    out, _ = resolve.resolve_rows(rows, scene={"obj:lamp"}, protagonist="person:clara",
                                  name_of=_name_of({}))
    assert out == [{"entity": "obj:lamp", "attribute": "in", "value": "person:clara",
                    "value_type": "entity"}]


# ---- Pin: ambiguous known candidates → no fresh entity ---------------------------
def test_ambiguous_match_does_not_mint():
    names = {"obj:thing_a": "thing", "obj:thing_b": "thing"}
    rows = [{"entity": "obj:thing", "attribute": "kind", "value": "thing"}]
    out, receipts = resolve.resolve_rows(rows, scene={"obj:thing_a", "obj:thing_b"},
                                         protagonist="person:p", name_of=_name_of(names))
    assert out == []                            # not minted, not mis-merged
    assert any(r[2] == "ambiguous" for r in receipts)


# ---- Cx 306: binding across obj:/place: must NOT retype the bound entity ---------
def test_cross_prefix_bind_drops_the_extractor_kind_row():
    # extractor emits `obj:street kind object` while `place:street` exists → bind obj:street →
    # place:street, but DROP the kind row (never retype an existing entity to "object").
    names = {"place:street": "street"}
    rows = [{"entity": "obj:street", "attribute": "kind", "value": "object"},
            {"entity": "obj:street", "attribute": "fog", "value": "thick"}]
    out, receipts = resolve.resolve_rows(rows, scene={"place:street"}, protagonist="person:p",
                                         name_of=_name_of(names))
    # the kind row is gone; the non-kind fact rebinds to the existing place
    assert {"entity": "place:street", "attribute": "kind", "value": "object"} not in out
    assert {"entity": "place:street", "attribute": "fog", "value": "thick"} in out
    assert any(r[2] == "bound_kind_skipped" for r in receipts)


# ---- Cx 306: free-text never MINTS a place (the move channel owns place creation) ----
def test_free_text_does_not_mint_a_place():
    rows = [{"entity": "place:back_room", "attribute": "kind", "value": "room"}]
    out, receipts = resolve.resolve_rows(rows, scene=set(), protagonist="person:p",
                                         name_of=_name_of({}))
    assert out == []                                  # a novel place from prose is dropped
    assert any(r[2] == "novel_denied" for r in receipts)
    # but the deterministic MOVE channel still mints a place (bind_or_mint signals mint on zero)
    assert resolve.bind_or_mint("the back room", kind="place", candidates=set(),
                                protagonist="person:p", name_of=_name_of({})) == (None, "mint")


# ---- Cx 308: a free-text obj whose KIND is place-like is denied (no obj:street split) ----
def test_free_text_obj_with_place_like_kind_denied():
    rows = [{"entity": "obj:street", "attribute": "kind", "value": "street"}]
    out, receipts = resolve.resolve_rows(rows, scene=set(), protagonist="person:pc",
                                         name_of=_name_of({}))
    assert out == []                                  # NOT a canon-ready obj:street row
    assert any(r[2] == "place_like_obj_denied" for r in receipts)


# ---- Cx 308: an obj mention must NOT bind to a known person (same-kind guard restored) ----
def test_obj_mention_does_not_bind_to_person():
    names = {"person:doctor": "Doctor Ames"}
    rows = [{"entity": "obj:doctor", "attribute": "kind", "value": "object"},
            {"entity": "obj:doctor", "attribute": "color", "value": "black"}]
    out, _ = resolve.resolve_rows(rows, scene={"person:doctor"}, protagonist="person:pc",
                                  name_of=_name_of(names))
    assert all(r["entity"] != "person:doctor" for r in out)   # never wrote facts onto the person
    assert any(r["entity"] == "obj:doctor" for r in out)      # the object minted as itself instead


# ---- Founder 2026-06-30: the PLAYER channel cannot conjure a person/place by fiat ----
def test_player_input_does_not_mint_a_person():
    # "I am Bradford Clemense" extracts a standalone person:bradford_clemense (alias 'I'); the player
    # channel must NOT mint it as a present NPC. Objects still mint (improv permanence).
    rows = [{"entity": "person:bradford_clemense", "attribute": "kind", "value": "person"},
            {"entity": "person:bradford_clemense", "attribute": "name", "value": "Bradford Clemense"}]
    out, receipts = resolve.resolve_rows(rows, scene=set(), protagonist="person:clara",
                                         name_of=_name_of({}),
                                         mint_kinds=resolve._PLAYER_INPUT_MINT_KINDS)
    assert out == []                                   # no phantom NPC
    assert any(r[2] == "novel_denied" for r in receipts)
    # an object the player names still mints under the player channel
    out2, _ = resolve.resolve_rows([{"entity": "obj:tin_cup", "attribute": "kind", "value": "cup"}],
                                   scene=set(), protagonist="person:clara", name_of=_name_of({}),
                                   mint_kinds=resolve._PLAYER_INPUT_MINT_KINDS)
    assert out2 == [{"entity": "obj:tin_cup", "attribute": "kind", "value": "cup"}]


# ---- novel improv still mints when allowed (a mug from the bar exists) -----------
def test_zero_candidate_novel_mints_when_allowed():
    rows = [{"entity": "obj:tin_cup", "attribute": "kind", "value": "cup"}]
    out, _ = resolve.resolve_rows(rows, scene=set(), protagonist="person:p",
                                  name_of=_name_of({}), allow_mint=True)
    assert out == rows                          # genuinely novel → kept (minted)
    out2, _ = resolve.resolve_rows(rows, scene=set(), protagonist="person:p",
                                   name_of=_name_of({}), allow_mint=False)
    assert out2 == []                           # mint not sanctioned → dropped


# ---- #98 FIRST-MENTION PERMANENCE (Cx 415, the 306 amendment) ---------------------

def test_is_proper_named_matrix():
    # the resolver-side predicate, NOT the session display helper: article-led venue
    # names are proper by convention; lowercase significant tokens are description.
    assert resolve.is_proper_named("The Hart and Bell")        # the live exhibit
    assert resolve.is_proper_named("John Johnson")
    assert resolve.is_proper_named("Dr. Ames")
    assert resolve.is_proper_named("Administrator Cray")
    assert resolve.is_proper_named("Brackenmere")
    assert resolve.is_proper_named("The Duke of Norfolk")
    assert not resolve.is_proper_named("the street")
    assert not resolve.is_proper_named("the yard")
    assert not resolve.is_proper_named("the wrapped crown")    # the display-helper pin
    assert not resolve.is_proper_named("street")
    assert not resolve.is_proper_named("a tall man")
    assert not resolve.is_proper_named("the landlord of the Hart and Bell")  # descriptive head
    assert not resolve.is_proper_named("")
    assert not resolve.is_proper_named(None)


_STUBS = resolve._NARRATION_STUB_KINDS
_NARR = resolve._NARRATION_MINT_KINDS


def test_narration_stub_mints_named_place_minimal():
    # a proper-named novel place stub-mints kind+name ONLY — description trims,
    # nothing stages, nothing relocates (Cx 415 #3).
    rows = [
        {"entity": "place:hart_and_bell", "attribute": "kind", "value": "inn"},
        {"entity": "place:hart_and_bell", "attribute": "name", "value": "The Hart and Bell"},
        {"entity": "place:hart_and_bell", "attribute": "description",
         "value": "a low coach-yard inn smelling of tallow"},
    ]
    out, receipts = resolve.resolve_rows(rows, scene={"place:study"},
                                         protagonist="person:p", name_of=_name_of({}),
                                         mint_kinds=_NARR, stub_kinds=_STUBS)
    got = {(r["attribute"]): r["value"] for r in out}
    assert got == {"kind": "inn", "name": "The Hart and Bell"}
    assert ("place:hart_and_bell", "description", "stub_trimmed") in receipts


def test_narration_stub_second_mention_binds_no_duplicate():
    # the stub exists → the next mention BINDS it (roster-wide bind-before-mint),
    # never a place:hart_and_bell_1 twin.
    names = {"place:hart_and_bell": "The Hart and Bell"}
    rows = [{"entity": "place:the_hart_and_bell", "attribute": "name",
             "value": "The Hart and Bell"}]
    out, receipts = resolve.resolve_rows(rows, scene={"place:hart_and_bell", "place:study"},
                                         protagonist="person:p", name_of=_name_of(names),
                                         mint_kinds=_NARR, stub_kinds=_STUBS)
    assert {r["entity"] for r in out} == {"place:hart_and_bell"}
    assert ("place:hart_and_bell", "name", "bound") in receipts


def test_narration_generic_places_still_never_mint():
    # the 306/308 anti-phantom bars hold: "the street"/"the yard" are description,
    # not names — no stub, no mint (the move channel owns places).
    rows = [
        {"entity": "place:street", "attribute": "kind", "value": "street"},
        {"entity": "place:street", "attribute": "name", "value": "the street"},
        {"entity": "place:yard", "attribute": "name", "value": "the yard"},
        {"entity": "obj:street", "attribute": "kind", "value": "street"},
    ]
    out, receipts = resolve.resolve_rows(rows, scene={"place:study"},
                                         protagonist="person:p", name_of=_name_of({}),
                                         mint_kinds=_NARR, stub_kinds=_STUBS)
    assert out == []
    assert ("obj:street", "kind", "place_like_obj_denied") in receipts


def test_narration_person_stub_needs_a_personal_name():
    # "John Johnson" stubs (kind/name/role only); "the landlord of the Hart and Bell"
    # is a descriptive phrase, not a person's name — denied (Cx 415 #3).
    rows = [
        {"entity": "person:john_johnson", "attribute": "kind", "value": "person"},
        {"entity": "person:john_johnson", "attribute": "name", "value": "John Johnson"},
        {"entity": "person:john_johnson", "attribute": "role", "value": "childhood friend"},
        {"entity": "person:john_johnson", "attribute": "in", "value": "place:study",
         "value_type": "entity"},
        {"entity": "person:landlord", "attribute": "kind", "value": "person"},
        {"entity": "person:landlord", "attribute": "name",
         "value": "the landlord of the Hart and Bell"},
    ]
    out, receipts = resolve.resolve_rows(rows, scene={"place:study"},
                                         protagonist="person:p", name_of=_name_of({}),
                                         mint_kinds=_NARR, stub_kinds=_STUBS)
    by_ent = {}
    for r in out:
        by_ent.setdefault(r["entity"], {})[r["attribute"]] = r["value"]
    assert set(by_ent) == {"person:john_johnson"}
    assert by_ent["person:john_johnson"] == {
        "kind": "person", "name": "John Johnson", "role": "childhood friend"}
    # the `in` row TRIMMED — a person stub is never staged by prose (Cx 415 #3)
    assert ("person:john_johnson", "in", "stub_trimmed") in receipts
    assert ("person:landlord", "kind", "novel_denied") in receipts


def test_stub_containment_binds_existing_place_or_drops():
    # a place stub may carry `in` ONLY toward a place that BINDS (Cx 415 #3); a novel
    # or unbound container drops the row, keeping kind/name.
    names = {"place:brackenmere": "Brackenmere"}
    rows = [
        {"entity": "place:hart_and_bell", "attribute": "name", "value": "The Hart and Bell"},
        {"entity": "place:hart_and_bell", "attribute": "in", "value": "place:brackenmere",
         "value_type": "entity"},
    ]
    out, _ = resolve.resolve_rows(rows, scene={"place:brackenmere"},
                                  protagonist="person:p", name_of=_name_of(names),
                                  mint_kinds=_NARR, stub_kinds=_STUBS)
    assert {(r["attribute"], r["value"]) for r in out} == {
        ("name", "The Hart and Bell"), ("in", "place:brackenmere")}
    # unbound container: the containment drops, the stub survives
    rows2 = [
        {"entity": "place:hart_and_bell", "attribute": "name", "value": "The Hart and Bell"},
        {"entity": "place:hart_and_bell", "attribute": "in", "value": "place:nowhere_named",
         "value_type": "entity"},
    ]
    out2, receipts2 = resolve.resolve_rows(rows2, scene=set(),
                                           protagonist="person:p", name_of=_name_of({}),
                                           mint_kinds=_NARR, stub_kinds=_STUBS)
    assert {(r["attribute"]) for r in out2} == {"name"}


def test_stub_never_enters_the_value_position():
    # pointing an EXISTING entity's `in` at a brand-new named place is a relocation
    # effect the stub gate does not own — the row drops (Cx 415 #3/#6).
    names = {"person:witness": "the witness"}
    rows = [
        {"entity": "person:witness", "attribute": "in", "value": "place:hart_and_bell",
         "value_type": "entity"},
        {"entity": "place:hart_and_bell", "attribute": "name", "value": "The Hart and Bell"},
    ]
    out, receipts = resolve.resolve_rows(rows, scene={"person:witness"},
                                         protagonist="person:p", name_of=_name_of(names),
                                         mint_kinds=_NARR, stub_kinds=_STUBS)
    assert {(r["entity"], r["attribute"]) for r in out} == {
        ("place:hart_and_bell", "name")}                     # the stub itself still lands
    assert ("place:hart_and_bell", "in", "stub_value_denied") in receipts


def test_player_input_channel_unchanged_no_person_no_place_stub():
    # the Bradford Clemense protection stays intact: player input gets NO stub gate —
    # a proper-named person/place in the player's own words never mints.
    rows = [
        {"entity": "person:bradford_clemense", "attribute": "name",
         "value": "Bradford Clemense"},
        {"entity": "place:hart_and_bell", "attribute": "name", "value": "The Hart and Bell"},
    ]
    out, receipts = resolve.resolve_rows(rows, scene=set(), protagonist="person:p",
                                         name_of=_name_of({}),
                                         mint_kinds=resolve._PLAYER_INPUT_MINT_KINDS)
    assert out == []
    reasons = {(e, why) for (e, _a, why) in receipts}
    assert ("person:bradford_clemense", "novel_denied") in reasons
    assert ("place:hart_and_bell", "novel_denied") in reasons


# ---- #98 live-probe finding (letter 442): reconstructed name evidence -------------

_PROBE_PROSE = ("Before Brackenmere Hall, you had a room at The Hart and Bell in "
                "Brackenmere village, above the coach yard.")


def test_reconstruct_names_recovers_cased_spans_from_prose():
    # the lean extractor emits kind rows with slug ids and NO name rows — the cased
    # surface form is recovered from the prose the host already holds; fail-closed
    # when no span exists.
    rows = [
        {"entity": "place:the_hart_and_bell", "attribute": "kind", "value": "inn"},
        {"entity": "place:brackenmere_village", "attribute": "kind", "value": "village"},
        {"entity": "place:coach_yard", "attribute": "kind", "value": "coach_yard"},
        {"entity": "place:nowhere_spoken", "attribute": "kind", "value": "room"},
        {"entity": "obj:lantern", "attribute": "kind", "value": "lantern"},  # not place/person
    ]
    syn = {r["entity"]: r["value"] for r in resolve.reconstruct_names(rows, _PROBE_PROSE)}
    assert syn["place:the_hart_and_bell"] == "The Hart and Bell"   # cased, verbatim
    assert syn["place:brackenmere_village"] == "Brackenmere village"
    assert syn["place:coach_yard"] == "coach yard"
    assert "place:nowhere_spoken" not in syn                       # no span → no evidence
    assert "obj:lantern" not in syn


def test_reconstructed_names_feed_the_stub_gate_end_to_end():
    # probe-shaped extraction (no name rows) + reconstruction → ONLY the proper-named
    # venue stubs (with its cased name); lowercase-in-prose places stay denied.
    rows = [
        {"entity": "place:the_hart_and_bell", "attribute": "kind", "value": "inn"},
        {"entity": "place:brackenmere_village", "attribute": "kind", "value": "village"},
        {"entity": "place:coach_yard", "attribute": "kind", "value": "coach_yard"},
    ]
    rows = rows + resolve.reconstruct_names(rows, _PROBE_PROSE)
    out, receipts = resolve.resolve_rows(rows, scene={"place:study"},
                                         protagonist="person:p", name_of=_name_of({}),
                                         mint_kinds=resolve._NARRATION_MINT_KINDS,
                                         stub_kinds=resolve._NARRATION_STUB_KINDS)
    by_ent = {}
    for r in out:
        by_ent.setdefault(r["entity"], {})[r["attribute"]] = r["value"]
        assert "_synthetic_name" not in r                          # the marker never commits
    assert set(by_ent) == {"place:the_hart_and_bell"}
    assert by_ent["place:the_hart_and_bell"] == {"kind": "inn", "name": "The Hart and Bell"}
    reasons = {(e, why) for (e, _a, why) in receipts}
    assert ("place:brackenmere_village", "novel_denied") in reasons
    assert ("place:coach_yard", "novel_denied") in reasons


def test_synthetic_name_never_reasserted_onto_a_bound_entity():
    # a bound entity's canon name is authoritative — the prose-cased reconstruction
    # commits ONLY with a stub mint.
    names = {"place:hart_and_bell": "The Hart and Bell"}
    rows = [{"entity": "place:the_hart_and_bell", "attribute": "kind", "value": "inn"}]
    rows = rows + resolve.reconstruct_names(rows, _PROBE_PROSE)
    out, receipts = resolve.resolve_rows(rows, scene={"place:hart_and_bell"},
                                         protagonist="person:p", name_of=_name_of(names),
                                         mint_kinds=resolve._NARRATION_MINT_KINDS,
                                         stub_kinds=resolve._NARRATION_STUB_KINDS)
    assert not any(r["attribute"] == "name" for r in out)
    assert ("place:hart_and_bell", "name", "synthetic_name_skipped") in receipts
