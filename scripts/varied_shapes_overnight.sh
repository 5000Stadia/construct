#!/bin/bash
# Shape-breadth overnight test (founder 2026-07-09): after the first critic
# campaign finishes, build + critic four deliberately CONTRASTING shapes the
# current shelf lacks — romance / legal-political / comedy-farce / heist — each
# also probing a different corner of the WORLD LAWS register gate (quiet social
# law / systemic-only REAL / single absurd law / scheme). SERIAL (Codex limit).
# Probe worlds are atticked after criticking so the live shelf stays clean.
cd /home/k/Newproject
export PYTHONPATH=.
L=logs/overnight-critic.log
# wait for the first campaign to finish (poll the completion marker)
until grep -q "CAMPAIGN COMPLETE" "$L" 2>/dev/null; do sleep 60; done
echo "###### SHAPE-BREADTH CAMPAIGN $(date) ######" >> "$L"

probe() {  # $1=name $2=reality ; seed on stdin
  local name="$1" reality="$2" seed; seed="$(cat)"
  echo "=== $(date '+%H:%M:%S') BUILD $name ($reality) ===" >> "$L"
  if echo "$seed" | timeout 2400 .venv/bin/python scripts/build_probe_world.py "$name" "$reality" >> "$L" 2>&1; then
    echo "=== $(date '+%H:%M:%S') CRITIC $name ===" >> "$L"
    timeout 1800 .venv/bin/python scripts/critic_harness.py "$name" standard >> "$L" 2>&1 || echo "=== $name critic exit $? ===" >> "$L"
  else
    echo "=== $name BUILD FAILED (exit $?) — skipping critic ===" >> "$L"
  fi
  # keep the live shelf clean: attic the probe (founder can un-attic from the report)
  mkdir -p worlds/attic
  mv worlds/$name.world worlds/$name.meta.json worlds/$name.images.json worlds/attic/ 2>/dev/null
  mv worlds/$name.*.world worlds/attic/ 2>/dev/null
  sleep 20
}

probe probe_romance real <<'S'
A second-chance romance in present-day Lisbon. Two people who loved each other in university and lost touch after a misunderstanding, brought back into each other's orbit when a mutual friend asks them both to help plan her wedding. Warm, bittersweet, adult, real-world; the drama is emotional and relational, not violent. The question is whether they can forgive the past and choose each other now.
S

probe probe_legal real <<'S'
A legal-political thriller in 1990s Washington D.C. A junior attorney at a powerful firm discovers a memo suggesting a Supreme Court vacancy was engineered — and the trail runs through her own senior partners. Tense, procedural, real-world exactly as it was: no invented agencies, real institutions, the informal code of loyalty against the law. She must decide how far to follow it and whom she can trust.
S

probe probe_farce secondary <<'S'
A screwball farce at a grand seaside hotel on opening night. The nervous understudy must impersonate a famous, feared opera diva for one performance — and everyone who could expose the swap keeps arriving at the worst possible moment: the diva's jealous rival, a besotted critic, the diva herself. Light, fast, comic, doors slamming; disaster is always one bad line away. The single absurd rule of this world: the hotel's old bell only rings for a lie told under its tower.
S

probe probe_heist real <<'S'
A stylish jewel heist in 1960s Monaco. A retired thief is pulled back for one last job: the casino's vault during the Grand Prix, when the whole principality is watching the cars. Assemble a crew with the right specialties, case the security, and pull the job in the chaos. Clever, tense, glamorous; the tension is timing and trust, not gunfire.
S

echo "###### SHAPE-BREADTH COMPLETE $(date) ######" >> "$L"
