"""Kick the tyres on PB's structured triage context (87b74b6): inspect the new
`auto_decline` struct on anchor2's real residue, classify each pair with the
code-first rule from letter 017, and exercise p.reject()/distinct_from sticking.
For PB letter 056. Fast, no LLM."""
import json
from patternbuffer import World

w = World("worlds/anchor2.world", world_id="w:anchor2")
p = w.porcelain
out = {}
try:
    props = p.proposals()
    out["count"] = len(props)
    out["raw"] = props

    # Code-first triage rule (017): relating edge (incl containment) -> reject;
    # no related edge + same kind + uncontested -> confirm-safe; else defer.
    def classify(pr):
        ad = pr.get("auto_decline") or {}
        code = ad.get("code")
        related = ad.get("related_rows") or []
        kinds = ad.get("kinds") or []
        if code in ("containment", "relating_edge") or related:
            return "reject (relating edge)"
        kvals = {k.get("value") for k in kinds}
        conflicted = any(k.get("conflicted") for k in kinds)
        if len(kvals) == 1 and not conflicted:
            return "confirm-safe (same kind, no relating edge)"
        return "defer (cross-kind / contested / generic)"
    out["classification"] = [
        {"a": pr["a"], "b": pr["b"], "code": (pr.get("auto_decline") or {}).get("code"),
         "decision": classify(pr)} for pr in props]

    # Exercise reject() + distinct_from sticking: reject the first proposal,
    # then re-run reconcile and confirm the pair is NOT re-proposed/merged.
    if props:
        a, b = props[0]["a"], props[0]["b"]
        out["reject_target"] = [a, b]
        out["reject_receipt"] = p.reject(a, b)
        re2 = p.reconcile()
        still = any({pr["a"], pr["b"]} == {a, b} for pr in p.proposals())
        merged_anyway = (w.registry.resolve(a) == w.registry.resolve(b))
        out["after_reject"] = {"reconcile": re2, "pair_reproposed": still,
                               "pair_merged_anyway": merged_anyway,
                               "distinct_sticks": (not still and not merged_anyway)}
finally:
    w.close()

print("\n==================== TRIAGE STRUCT SCORECARD ====================")
print(json.dumps(out, indent=2, default=str))
print("=================================================================")
