"""Host-control key policy — the arc/destination bookkeeping the HOST owns.

The ``arc:`` namespace is the host-control portfolio: ``arc:portfolio`` (the
manifest), ``arc:main`` / ``arc:cheap`` (the live arcs), and the
``arc:tangent_*`` / ``arc:replan_*`` / ``arc:ep_*`` / ``arc:gen_*`` bookkeeping
rows. These are NOT world facts — they are the host's own destination-layer
state. A *conflicted* read on one means a mid-play writer appended without first
retracting the sealed rows (the EP2 stale-arc serve, Cx 167): the engine serves
its earliest holding value and the reopened episode silently runs the OLD arc.

Unlike an ordinary fact, silently collapsing that conflict hides a host bug, so a
conflicted host-control read is always surfaced (telemetry, not a fix — the value
served is unchanged).

pbeo review (2026-07-28): the original guard warned for the literal
``arc:portfolio`` only, while the same failure mode is available to every key in
the class. "A correction names its class and sweeps it, or it is a patch." This
module IS that class, in one place, so the four independent known/conflicted →
value collapse sites (adapter/foyer/clock/game) share one policy.
"""

import logging

logger = logging.getLogger(__name__)

_HOST_CONTROL_PREFIX = "arc:"


def is_host_control(entity: object) -> bool:
    """Whether ``entity`` is a host-control key (the ``arc:`` destination-layer
    namespace), for which a conflicted read is a host defect to surface loudly
    rather than an ordinary fact to collapse silently."""
    return isinstance(entity, str) and entity.startswith(_HOST_CONTROL_PREFIX)


def collapse_state(st: object, entity: str, attribute: str) -> object:
    """Unwrap a porcelain ``state()`` result to its bare canon value, applying the
    single host-control conflict policy in one place.

    - unknown / frontier → ``None`` (indeterminate to the atoms)
    - known → the value
    - conflicted → the engine's holding value, BUT when ``entity`` is host-control
      the collapse is surfaced loudly (the EP2/Cx-167 unretracted-append defect
      this class-wide guard exists to catch).

    Callers keep their own ``state()`` call (with their own ``as_of`` / ``frame``)
    and pass the already-fetched result here, so horizon and frame semantics are
    unchanged — only the collapse policy is centralized.
    """
    if not isinstance(st, dict):
        return None
    status = st.get("status")
    if status == "known":
        return (st.get("fact") or {}).get("value")
    if status == "conflicted":
        value = (st.get("fact") or {}).get("value")
        if is_host_control(entity):
            logger.warning(
                "CONFLICTED read on host-control %s.%s — serving the holding value "
                "%r; a mid-play writer must retract the sealed rows before appending",
                entity, attribute, value)
        return value
    return None
