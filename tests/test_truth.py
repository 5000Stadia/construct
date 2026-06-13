from construct.arc.truth import Truth, t_all, t_any, t_at_least, t_not

T, F, I = Truth.TRUE, Truth.FALSE, Truth.INDETERMINATE


def test_not():
    assert t_not(T) is F
    assert t_not(F) is T
    assert t_not(I) is I


def test_all():
    assert t_all([T, T]) is T
    assert t_all([T, F]) is F
    assert t_all([T, I]) is I
    assert t_all([F, I]) is F  # FALSE dominates
    assert t_all([]) is T


def test_any():
    assert t_any([F, T]) is T
    assert t_any([F, F]) is F
    assert t_any([F, I]) is I
    assert t_any([T, I]) is T  # TRUE dominates
    assert t_any([]) is F


def test_at_least():
    assert t_at_least(2, [T, T, F]) is T
    assert t_at_least(2, [T, F, F]) is F
    assert t_at_least(2, [T, I, F]) is I  # the open one could flip it
    assert t_at_least(2, [T, I, I]) is I
    assert t_at_least(3, [T, I, F]) is F  # even all-INDET-true can't reach
