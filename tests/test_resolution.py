"""Action-resolution deck (ACTION-RESOLUTION.md): the pre-rolled outcome bag honors
the 10/20/55/15 distribution, draws sequentially, refills, and persists seed+cursor."""
from collections import Counter

from construct import resolution
from tests.test_integration import world  # noqa: F401


class FakeWorld:
    """Minimal world: an in-memory session-frame store + a porcelain.ingest_structured
    that writes it, plus a reads-like `.state`."""
    def __init__(self):
        self.rows: dict[tuple, str] = {}
        self.porcelain = self

    def ingest_structured(self, items, frame=None, classify="inline"):
        for it in items:
            self.rows[(it["entity"], it["attribute"])] = str(it["value"])
        return {"rows": items}

    def state(self, entity, attribute, frame=None, as_of=None):
        return self.rows.get((entity, attribute))


def test_bag_is_exactly_the_distribution():
    c = Counter(resolution._BAG)
    assert c == {"terrible_failure": 10, "failure_opportunity": 20,
                 "success_cost": 55, "complete_success": 15}
    assert len(resolution._BAG) == 100


def test_a_batch_is_a_permutation_honoring_the_ratio():
    bag = resolution._batch(seed=12345, index=0)
    assert Counter(bag) == Counter(resolution._BAG)        # same multiset, shuffled
    assert resolution._batch(12345, 0) == bag              # deterministic in (seed,index)
    assert resolution._batch(12345, 1) != bag              # next batch differs


def test_draw_advances_cursor_and_persists():
    w = FakeWorld()
    t1 = resolution.draw_tier(w, w, seed_source=999)
    assert t1 in resolution.TIERS
    assert w.rows[(resolution._DECK_ENTITY, resolution._CURSOR)] == "1"
    assert w.rows[(resolution._DECK_ENTITY, resolution._SEED)] == "999"
    t2 = resolution.draw_tier(w, w)                         # seed now persisted
    assert w.rows[(resolution._DECK_ENTITY, resolution._CURSOR)] == "2"
    # the two draws match the seeded batch order
    assert [t1, t2] == resolution._batch(999, 0)[:2]


def test_100_draws_yield_the_exact_distribution_then_refill():
    w = FakeWorld()
    drawn = [resolution.draw_tier(w, w, seed_source=7) for _ in range(100)]
    assert Counter(drawn) == Counter(resolution._BAG)      # exact over a full bag
    assert w.rows[(resolution._DECK_ENTITY, resolution._CURSOR)] == "100"
    # draw 101 refills (next batch) without error
    assert resolution.draw_tier(w, w) in resolution.TIERS
    assert w.rows[(resolution._DECK_ENTITY, resolution._CURSOR)] == "101"


def test_directive_renders_the_tier_without_exposing_dice():
    d = resolution.directive("success_cost", "the pit may be too wide")
    assert "SUCCESS WITH A COST" in d
    assert "the pit may be too wide" in d
    assert "do not state odds, dice" in d.lower() or "no" in d.lower()


def test_draws_advance_through_a_real_engine_world(world):  # noqa: F811
    """The deck's seed and cursor live as rewritten session rows; on the real engine
    each draw must read the LATEST cursor, never a stale holding value (Ironhold
    probe run 4: the cursor read stuck at 1, so every check drew the same card)."""
    from construct.adapter import PorcelainWorldReads
    drawn = [resolution.draw_tier(PorcelainWorldReads(world), world.porcelain,
                                  seed_source=999) for _ in range(6)]
    assert drawn == resolution._batch(999, 0)[:6]
    assert resolution._state(PorcelainWorldReads(world)) == (999, 6)


def test_a_world_with_old_undeclared_deck_rows_still_draws(world):  # noqa: F811
    """A world that drew before the deck rows were declared holds undeclared
    `seed`/`cursor` rows, and the engine refuses to declare an attribute that
    already holds data; the declared new names keep such a world drawing."""
    from construct.adapter import PorcelainWorldReads
    world.porcelain.ingest_structured([
        {"entity": resolution._DECK_ENTITY, "attribute": a, "value": v, "timeless": True}
        for a, v in (("seed", "5"), ("cursor", "1"), ("cursor", "2"))
    ], frame=resolution.SESSION, classify="rules")
    drawn = [resolution.draw_tier(PorcelainWorldReads(world), world.porcelain,
                                  seed_source=999) for _ in range(3)]
    assert drawn == resolution._batch(999, 0)[:3]
