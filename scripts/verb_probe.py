"""Exercise PB's host-reconciliation verbs (b2ecbff) against anchor2's real
residue: enumerate proposals, triage by the kind-pair decline reason, confirm
the genuine coreferents, reject the false-positives, and probe the edge cases
(veto names the edge / no_proposal / noop_already_merged). For PB letter 054."""
import json
from patternbuffer import World

w = World("worlds/anchor2.world", world_id="w:anchor2")
p = w.porcelain
out = {}
try:
    props = p.proposals()
    out["proposals_enumerated"] = props
    out["count"] = len(props)

    # Triage by the kind-pair decline reason I asked for in 014.
    def kindpair(pr):
        return (pr.get("auto_decline_reason") or "")
    genuine, reject = [], []
    for pr in props:
        r = kindpair(pr)
        # object<->place cross-kind = plausibly one referent (vault); person<->person
        # alias_not_specific = same person (cray). obj<->person / person<->place = reject.
        if "object↔place" in r or "obj↔place" in r or "alias_not_specific" in r or "kind_absent" in r:
            genuine.append(pr)
        else:
            reject.append(pr)
    out["triage_confirm"] = [(pr["a"], pr["b"], kindpair(pr)) for pr in genuine]
    out["triage_reject"] = [(pr["a"], pr["b"], kindpair(pr)) for pr in reject]

    # Confirm the genuine coreferents.
    receipts = []
    for pr in genuine:
        rcpt = p.confirm(pr["a"], pr["b"])
        receipts.append({"pair": [pr["a"], pr["b"]], "reason": kindpair(pr), "receipt": rcpt})
    out["confirm_receipts"] = receipts

    # Verify the genuine clusters collapsed.
    checks = {}
    for a, b in [("obj:vault", "place:records_vault"), ("obj:vault", "place:vault"),
                 ("person:cray", "person:administrator_cray")]:
        try:
            checks[f"{a}=={b}"] = (w.registry.resolve(a) == w.registry.resolve(b))
        except Exception as ex:
            checks[f"{a}=={b}"] = f"ERR {ex}"
    out["post_confirm_collapsed"] = checks

    # Edge case: veto must fire + name the edge on a container<->contents pair.
    cont = next(((r.entity, r.value) for r in w.buffer.visible()
                 if r.attribute in ("in", "contains", "holds")
                 and isinstance(r.value, str) and r.value.startswith(("obj:", "place:"))), None)
    if cont:
        a, b = cont
        out["veto_test_pair"] = [a, b, "(a containment edge relates them)"]
        out["veto_test_receipt"] = p.merge(a, b, evidence="probe: should be vetoed")

    # Edge case: confirm on a non-proposal.
    out["no_proposal_test"] = p.confirm("obj:bottle", "place:office")

    # Edge case: noop on an already-merged pair (re-confirm a genuine one).
    if genuine:
        a, b = genuine[0]["a"], genuine[0]["b"]
        out["noop_test"] = p.confirm(a, b)
finally:
    w.close()

print("\n==================== VERB SCORECARD ====================")
print(json.dumps(out, indent=2, default=str))
print("========================================================")
