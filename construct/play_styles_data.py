"""Game-type cards — GENERATED from docs/design/GAME-TYPE-TAXONOMY.md
by scripts/build_play_styles.py. Do not hand-edit; edit the taxonomy MD
and re-run. Keyed by a slug of the card name."""

STYLE_CARDS = {
    'mystery_whodunnit': {
        'name': 'Mystery / Whodunnit',
        'family': 'Investigation & Epistemics',
        'directive': 'PLAY STYLE — MYSTERY / WHODUNNIT: Dwell on clues, witness testimony, scenes of evidence, contradictions between accounts, motives, history, red herrings, and the player’s deductions. Compress travel, routine logistics, and the passage between clue locations. Let tension build as accretion — the noose tightens as facts align and suspects squirm. Make victory mean name the truth or make the correct accusation, supported by what was uncovered; make loss come from a wrong accusation, a missed clue, or the trail going cold.',
    },
    'detective_procedural': {
        'name': 'Detective Procedural',
        'family': 'Investigation & Epistemics',
        'directive': 'PLAY STYLE — DETECTIVE PROCEDURAL: Dwell on chain of evidence, interrogation technique, alibis, canvassing, records, forensics, admissibility, and the moment a fact locks a theory. Compress pure flashes of genius, unrelated personal life, and travel between steps. Let tension build as accretion under a procedural clock — brick by brick while time or rules press. Make victory mean close the case with corroborated evidence and method intact; make loss come from evidence is tainted, an alibi holds, a witness recants, or the deadline passes.',
    },
    'forensic_reconstruction': {
        'name': 'Forensic Reconstruction',
        'family': 'Investigation & Epistemics',
        'directive': 'PLAY STYLE — FORENSIC RECONSTRUCTION: Dwell on measurements, residues, wounds, breakage, trajectories, timestamps, lab results, and competing reconstructions of the event. Compress dramatic hunches not grounded in traces, social melodrama, and broad travel. Let tension build as analytic accretion — tiny physical facts narrow possibility space. Make victory mean reconstruct what happened with enough precision to act on it; make loss come from misread the evidence, contaminate the scene, or build a reconstruction that later breaks.',
    },
    'cold_case_archive_dive': {
        'name': 'Cold Case / Archive Dive',
        'family': 'Investigation & Epistemics',
        'directive': 'PLAY STYLE — COLD CASE / ARCHIVE DIVE: Dwell on old files, photographs, letters, tapes, forgotten witnesses, decayed scenes, institutional memory, and the pain of delayed truth. Compress current action spectacle and fast resolution. Let tension build as slow thaw — dormant evidence warms into a live case as contradictions surface. Make victory mean solve or meaningfully reframe the old truth and bring closure, justice, or release; make loss come from records are missing, witnesses die or refuse, memory misleads, or the past stays buried.',
    },
    'conspiracy_paranoia': {
        'name': 'Conspiracy / Paranoia',
        'family': 'Investigation & Epistemics',
        'directive': 'PLAY STYLE — CONSPIRACY / PARANOIA: Dwell on surveillance, watchers, widening scope, ambiguous allies, near exposures, disinformation, and the rising cost of knowing. Compress mundane routine, tidy answers, and ordinary safety. Let tension build as escalating dread — scope and danger widen together while trust contracts. Make victory mean expose the system irreversibly, escape with the truth, or survive knowing enough to act; make loss come from silenced, discredited, co-opted, or spiraling into a false paranoid accusation.',
    },
    'journalistic_expos': {
        'name': 'Journalistic Exposé',
        'family': 'Investigation & Epistemics',
        'directive': 'PLAY STYLE — JOURNALISTIC EXPOSÉ: Dwell on source cultivation, document verification, editorial judgment, legal threat, intimidation, leaks, and the ethical cost of publication. Compress gunplay, courtroom finality, and unrelated newsroom color. Let tension build as pressure cooker — verification races retaliation and publication deadlines. Make victory mean publish a defensible story that changes public reality while protecting essential sources; make loss come from the story is wrong, spiked, discredited, legally destroyed, or sources are burned.',
    },
    'occult_research': {
        'name': 'Occult Research',
        'family': 'Investigation & Epistemics',
        'directive': 'PLAY STYLE — OCCULT RESEARCH: Dwell on grimoires, symbols, ritual correspondences, folklore, omens, taboo, partial translations, and the danger of using knowledge. Compress ordinary investigation legwork when it adds no lore, mundane travel, and clean scientific certainty. Let tension build as dreadful accretion — each fact grants leverage and contamination. Make victory mean identify the occult rule and use, bind, appease, or avoid it before it consumes you; make loss come from misinterpret the rite, violate a taboo, invite the force in, or pay too much for knowledge.',
    },
    'scientific_anomaly': {
        'name': 'Scientific Anomaly',
        'family': 'Investigation & Epistemics',
        'directive': 'PLAY STYLE — SCIENTIFIC ANOMALY: Dwell on experiments, instruments, anomalies, false hypotheses, controlled tests, peer dispute, and the discovery of a governing pattern. Compress pure mysticism, generic combat, and unrelated character drama. Let tension build as hypothesis ratchet — each test clarifies the rule while risk rises. Make victory mean produce a working model and use it to contain, exploit, or survive the anomaly; make loss come from trust a false model, trigger escalation, or fail to test before the window closes.',
    },
    'archaeological_decoding': {
        'name': 'Archaeological Decoding',
        'family': 'Investigation & Epistemics',
        'directive': 'PLAY STYLE — ARCHAEOLOGICAL DECODING: Dwell on ruins, stratigraphy, symbols, languages, grave goods, ritual spaces, contested interpretations, and the ethics of taking artifacts. Compress modern logistics and generic treasure grabbing. Let tension build as layered revelation — context changes the meaning of each prior find. Make victory mean understand the site, unlock its secret, or return with knowledge preserved; make loss come from destroy context, mistranslate the culture, trigger old defenses, or loot without understanding.',
    },
    'identity_memory_mystery': {
        'name': 'Identity / Memory Mystery',
        'family': 'Investigation & Epistemics',
        'directive': 'PLAY STYLE — IDENTITY / MEMORY MYSTERY: Dwell on fragmented memories, aliases, familiar strangers, body clues, records, personality discontinuities, and revelations that reframe prior choices. Compress routine detective logistics and external plot not tied to identity. Let tension build as destabilizing accretion — each fact both clarifies and threatens the self. Make victory mean establish the true identity and decide what to do with it; make loss come from accept a false self, lose agency to erased memory, or learn too late to act.',
    },
    'social_deduction_impostor_hunt': {
        'name': 'Social Deduction / Impostor Hunt',
        'family': 'Investigation & Epistemics',
        'directive': 'PLAY STYLE — SOCIAL DEDUCTION / IMPOSTOR HUNT: Dwell on accusations, alibis, voting blocs, behavioral tells, partial reveals, false certainty, and the politics of trust. Compress external plot and evidence that removes the social uncertainty too early. Let tension build as paranoia accretion with vote or reveal spikes. Make victory mean identify and remove the impostor, or survive as the hidden role by steering suspicion; make loss come from execute the wrong person, reveal too much, trust the liar, or fail to convince the group.',
    },
    'puzzle_escape': {
        'name': 'Puzzle / Escape',
        'family': 'Puzzle, Escape & Decoding',
        'directive': 'PLAY STYLE — PUZZLE / ESCAPE: Dwell on mechanisms, objects, clues, affordances, feedback, layered aha moments, and the satisfying click of a solution. Compress combat, social nuance, broad plot, and travel. Let tension build as gated accretion — discrete unlocks reveal the next obstacle. Make victory mean open the final way, escape, assemble the mechanism, or reach the locked goal; make loss come from be stuck with no progress or run out the clock where time matters.',
    },
    'puzzle_box_mechanism': {
        'name': 'Puzzle Box / Mechanism',
        'family': 'Puzzle, Escape & Decoding',
        'directive': 'PLAY STYLE — PUZZLE BOX / MECHANISM: Dwell on moving parts, inscriptions, tactile feedback, hidden compartments, state changes, partial successes, and mechanical logic. Compress external drama and unrelated exploration. Let tension build as nested reveal — each solved layer exposes a deeper one. Make victory mean fully open, repair, activate, or disarm the mechanism; make loss come from jam it, break it, trigger its failsafe, or fail to learn its states.',
    },
    'environmental_puzzle': {
        'name': 'Environmental Puzzle',
        'family': 'Puzzle, Escape & Decoding',
        'directive': 'PLAY STYLE — ENVIRONMENTAL PUZZLE: Dwell on spatial layout, cause and effect, environmental state, sightlines, physics, and experiments that visibly change the place. Compress dialogue, lore dumps, and abstract riddles not embodied in space. Let tension build as spatial gating — new paths appear as the environment is understood. Make victory mean make the environment assume the needed configuration and pass through; make loss come from misconfigure the space, trap yourself, waste the window, or trigger danger.',
    },
    'codebreaking_cryptography': {
        'name': 'Codebreaking / Cryptography',
        'family': 'Puzzle, Escape & Decoding',
        'directive': 'PLAY STYLE — CODEBREAKING / CRYPTOGRAPHY: Dwell on frequency, structure, repeated symbols, partial keys, false plaintext, translation choices, and the moment nonsense becomes message. Compress action unrelated to decoding and arbitrary guessing without feedback. Let tension build as analytic accretion — fragments become grammar, then command or revelation. Make victory mean decode enough to act, open access, reveal a secret, or transmit safely; make loss come from misdecode, reveal yourself, send the wrong command, or miss the time window.',
    },
    'riddle_trial': {
        'name': 'Riddle Trial',
        'family': 'Puzzle, Escape & Decoding',
        'directive': 'PLAY STYLE — RIDDLE TRIAL: Dwell on wordplay, metaphor, double meanings, cultural context, precise phrasing, and the danger of answering too literally. Compress combat, travel, and unrelated exposition. Let tension build as taut set-piece — pressure holds on the answer and its interpretation. Make victory mean answer correctly or frame the response that satisfies the trial; make loss come from answer wrongly, violate the form, or misunderstand the symbolic rule.',
    },
    'time_loop_optimization': {
        'name': 'Time-Loop Optimization',
        'family': 'Puzzle, Escape & Decoding',
        'directive': 'PLAY STYLE — TIME-LOOP OPTIMIZATION: Dwell on repetition with variation, schedules, causal chains, saved knowledge, failed attempts, and the evolving perfect route. Compress new-world exposition after rules are clear and unrepeated mundane actions. Let tension build as iterative spiral — frustration becomes mastery as the loop is mapped. Make victory mean execute the needed sequence and break, exploit, or resolve the loop; make loss come from waste loops, mis-sequence actions, lose memory, or solve the wrong problem.',
    },
    'route_optimization': {
        'name': 'Route Optimization',
        'family': 'Puzzle, Escape & Decoding',
        'directive': 'PLAY STYLE — ROUTE OPTIMIZATION: Dwell on maps, schedules, bottlenecks, tradeoffs, alternate paths, timing windows, and the cost of backtracking. Compress moment-by-moment scenery when route choice is settled. Let tension build as planning ratchet — options narrow as costs accumulate. Make victory mean reach objectives within the constraints with acceptable losses; make loss come from arrive too late, run out of resources, or choose a path that closes the goal.',
    },
    'team_coordination_puzzle': {
        'name': 'Team Coordination Puzzle',
        'family': 'Puzzle, Escape & Decoding',
        'directive': 'PLAY STYLE — TEAM COORDINATION PUZZLE: Dwell on asymmetric clues, timing calls, miscommunication, role handoffs, synchronized switches, and shared aha moments. Compress solo deduction and action that ignores teammates. Let tension build as coordination spikes — calm analysis interrupted by timed synchronization. Make victory mean combine partial knowledge and perform the coordinated solution; make loss come from miscommunicate, desynchronize, duplicate effort, or leave a role unserved.',
    },
    'trap_room_death_puzzle': {
        'name': 'Trap Room / Death Puzzle',
        'family': 'Puzzle, Escape & Decoding',
        'directive': 'PLAY STYLE — TRAP ROOM / DEATH PUZZLE: Dwell on hazards, timers, bodily risk, pressure plates, blades, poison, flooding, panic, and the clarity needed under fear. Compress slow lore, broad setting, and relaxed experimentation without cost. Let tension build as hard-clock ratchet — each mistake or delay makes the room deadlier. Make victory mean solve and survive before the trap completes; make loss come from die, maim someone, trigger the trap, or panic into the wrong action.',
    },
    'arg_transmedia_hunt': {
        'name': 'ARG / Transmedia Hunt',
        'family': 'Puzzle, Escape & Decoding',
        'directive': 'PLAY STYLE — ARG / TRANSMEDIA HUNT: Dwell on artifact texture, medium shifts, hidden channels, collaborative discovery, meta-clues, and the thrill of crossing boundaries. Compress linear exposition and single-room puzzle logic. Let tension build as distributed accretion — clues assemble from many places into a meta-answer. Make victory mean assemble the meta-solution, reach the hidden event, or unlock the next layer; make loss come from miss a channel, trust a fake clue, fragment the group, or arrive too late.',
    },
    'heist': {
        'name': 'Heist',
        'family': 'Schemes & Infiltration',
        'directive': 'PLAY STYLE — HEIST: Dwell on casing, roles, specialties, security seams, timing, complications, improvisation, and the getaway. Compress downtime, spending the take, and routine travel. Let tension build as quiet build to hard ratchet — the job turns every beat dangerous. Make victory mean secure the score and get out clean with crew and trail intact; make loss come from lose the take, lose the crew, get caught, or become traceable.',
    },
    'infiltration_stealth': {
        'name': 'Infiltration / Stealth',
        'family': 'Schemes & Infiltration',
        'directive': 'PLAY STYLE — INFILTRATION / STEALTH: Dwell on sightlines, patrol patterns, shadow, sound, cover, the body in space, and near-detection. Compress open combat, travel to the site, and objective details before arrival. Let tension build as accreting tightness with spikes — deeper entry, closer calls. Make victory mean reach the objective and exit undetected or without a trace that matters; make loss come from alarm, capture, cornering, or being forced into an unwinnable fight.',
    },
    'con_grift': {
        'name': 'Con / Grift',
        'family': 'Schemes & Infiltration',
        'directive': 'PLAY STYLE — CON / GRIFT: Dwell on the mark’s wants, tells, greed, shame, vanity, the persona’s upkeep, supporting details, and recovery when the lie slips. Compress physical security, violence, and unrelated logistics. Let tension build as accretion toward the sting — exposure risk climbs as trust deepens. Make victory mean the mark hands it over willingly and ideally never knows; make loss come from you are made, the mark turns the tables, or one detail unravels the story.',
    },
    'espionage_spycraft': {
        'name': 'Espionage / Spycraft',
        'family': 'Schemes & Infiltration',
        'directive': 'PLAY STYLE — ESPIONAGE / SPYCRAFT: Dwell on dead drops, cover stories, surveillance detection, asset fragility, handlers, double-cross, and the cost of betrayal. Compress the wider war except as pressure, routine cover life, and flashy action not tied to secrecy. Let tension build as slow warming with exposure spikes. Make victory mean move the secret, protect or extract the asset, or identify the mole without blowing the network; make loss come from the network is rolled up, the asset is burned, or you are turned or exposed.',
    },
    'undercover_operation': {
        'name': 'Undercover Operation',
        'family': 'Schemes & Infiltration',
        'directive': 'PLAY STYLE — UNDERCOVER OPERATION: Dwell on cover maintenance, bonding with targets, loyalty tests, moral compromise, slips, suspicion, and the split between role and self. Compress external investigation not tied to cover and action that blows the premise too early. Let tension build as identity pressure — deeper access increases both success and contamination. Make victory mean complete the mission without exposure and leave with self and evidence intact; make loss come from be exposed, converted, trapped by loyalties, or commit too much to the role.',
    },
    'prison_break': {
        'name': 'Prison Break',
        'family': 'Schemes & Infiltration',
        'directive': 'PLAY STYLE — PRISON BREAK: Dwell on daily routines, guards, blind spots, contraband, alliances, tunnels, forged papers, and the moment the window opens. Compress life outside and unrelated backstory. Let tension build as preparation ratchet to a narrow execution window. Make victory mean escape confinement and avoid immediate recapture; make loss come from the plan is discovered, allies betray you, the window closes, or recapture follows.',
    },
    'smuggling_run': {
        'name': 'Smuggling Run',
        'family': 'Schemes & Infiltration',
        'directive': 'PLAY STYLE — SMUGGLING RUN: Dwell on concealment methods, routes, checkpoints, bribes, patrols, cargo risk, and decisions about dumping or protecting the load. Compress the cargo’s wider politics unless it affects the run. Let tension build as route pressure with inspection spikes. Make victory mean deliver the cargo intact without unacceptable heat or loss; make loss come from cargo is seized, exposed, betrayed, damaged, or costs more than the run can bear.',
    },
    'sabotage_mission': {
        'name': 'Sabotage Mission',
        'family': 'Schemes & Infiltration',
        'directive': 'PLAY STYLE — SABOTAGE MISSION: Dwell on target systems, weak points, timing, planted faults, plausible deniability, cascading effects, and escape before the failure is traced. Compress general combat and broad strategy beyond the target. Let tension build as delayed ratchet — tension peaks at both planting and detonation. Make victory mean the target fails when needed and blame does not land on you; make loss come from the sabotage is found, mistimed, repaired, or causes catastrophic blowback.',
    },
    'rescue_extraction': {
        'name': 'Rescue / Extraction',
        'family': 'Schemes & Infiltration',
        'directive': 'PLAY STYLE — RESCUE / EXTRACTION: Dwell on the captive’s condition, route to them, guards or hazards, protection under movement, and hard choices about speed versus safety. Compress the politics of why unless it affects extraction. Let tension build as inward-outward ratchet — tension peaks reaching the target, then escaping with added burden. Make victory mean extract the person alive and get them to safety; make loss come from the target dies, refuses, is moved, or escape fails after contact.',
    },
    'fugitive_evasion': {
        'name': 'Fugitive Evasion',
        'family': 'Schemes & Infiltration',
        'directive': 'PLAY STYLE — FUGITIVE EVASION: Dwell on aliases, disguises, surveillance avoidance, exhausted movement, compromised contacts, wanted notices, and the fear of recognition. Compress long sanctuary, fixed homes, and unrelated goals. Let tension build as sustained pressure — safety decays as the net tightens. Make victory mean reach sanctuary, clear your name, disappear, or turn the hunt back on itself; make loss come from capture, exposure, betrayal by a contact, or running out of options.',
    },
    'manhunt_bounty_hunt': {
        'name': 'Manhunt / Bounty Hunt',
        'family': 'Schemes & Infiltration',
        'directive': 'PLAY STYLE — MANHUNT / BOUNTY HUNT: Dwell on sign, informants, last sightings, target psychology, terrain, competing hunters, moral choice at capture, and the closing net. Compress random wandering and combat before the hunt has located the target. Let tension build as converging pressure — uncertainty narrows into confrontation. Make victory mean find and capture, kill, recruit, or release the target according to the mission; make loss come from lose the trail, misidentify the target, arrive too late, or become the hunted.',
    },
    'blackmail_leverage': {
        'name': 'Blackmail / Leverage',
        'family': 'Schemes & Infiltration',
        'directive': 'PLAY STYLE — BLACKMAIL / LEVERAGE: Dwell on the secret, proof, pressure level, intermediaries, deniability, counter-leverage, and the target’s breaking point. Compress physical force and moralizing that avoids the leverage game. Let tension build as knife-edge accretion — power rises with exposure risk. Make victory mean secure compliance, concession, silence, or protection without blowback; make loss come from the secret is false, exposure backfires, retaliation lands, or you become worse than the target.',
    },
    'tactical_combat': {
        'name': 'Tactical Combat',
        'family': 'Action, Combat & Pursuit',
        'directive': 'PLAY STYLE — TACTICAL COMBAT: Dwell on terrain, initiative, enemy tactics, resource spend, cover, range, objective pressure, and the turning point. Compress travel between fights and long quiet stretches. Let tension build as episodic spikes with campaign attrition. Make victory mean win the engagement or objective with survivable losses; make loss come from the party falls, the objective is lost, or attrition prevents continuation.',
    },
    'cinematic_action': {
        'name': 'Cinematic Action',
        'family': 'Action, Combat & Pursuit',
        'directive': 'PLAY STYLE — CINEMATIC ACTION: Dwell on chases, leaps, narrow escapes, choreography, hazards, one-liners, momentum, and audacious improvisation. Compress realistic logistics, recovery, and granular tactical accounting. Let tension build as episodic spikes escalating toward a showdown. Make victory mean pull off the daring feat, beat the villain, and survive with style; make loss come from the stunt fails, the villain wins the beat, or momentum dies and you are pinned.',
    },
    'duel_standoff': {
        'name': 'Duel / Standoff',
        'family': 'Action, Combat & Pursuit',
        'directive': 'PLAY STYLE — DUEL / STANDOFF: Dwell on stillness, tells, stance, intent, breath, ritual, honor, the decisive exchange, and aftermath. Compress the wider battle, multiple foes, and surrounding noise. Let tension build as single taut ratchet — pressure coils then releases. Make victory mean land the decisive blow, win the exchange, or force yielding; make loss come from misread, hesitate, break form, or lose the moment.',
    },
    'boss_fight': {
        'name': 'Boss Fight',
        'family': 'Action, Combat & Pursuit',
        'directive': 'PLAY STYLE — BOSS FIGHT: Dwell on tells, arenas, phase shifts, counters, resource windows, failures that teach, and the final vulnerability. Compress generic minions and broad travel. Let tension build as learning spike — repeated danger becomes pattern mastery. Make victory mean defeat, banish, disable, or outlast the boss by mastering its pattern; make loss come from fail to adapt, exhaust resources, or misread the phase change.',
    },
    'monster_hunt': {
        'name': 'Monster Hunt',
        'family': 'Action, Combat & Pursuit',
        'directive': 'PLAY STYLE — MONSTER HUNT: Dwell on signs, lore, spoor, habits, victims, traps, tools, proximity dread, and preparation paying off. Compress unrelated subplots and generic travel. Let tension build as investigative build to climactic spike. Make victory mean slay, capture, banish, or redirect the creature by using what was learned; make loss come from wrong preparation, lost trail, beast escape, or hunter becoming prey.',
    },
    'raid_assault': {
        'name': 'Raid / Assault',
        'family': 'Action, Combat & Pursuit',
        'directive': 'PLAY STYLE — RAID / ASSAULT: Dwell on approach, breach, suppression, objectives, role coordination, alarms, fallback plans, and extraction under fire. Compress long planning unless it changes the assault and routine aftermath. Let tension build as fast ratchet — once begun, the tempo rarely stops. Make victory mean take or destroy the objective and withdraw with acceptable losses; make loss come from stall, lose surprise, suffer unacceptable casualties, or fail the objective.',
    },
    'siege_defense_last_stand': {
        'name': 'Siege Defense / Last Stand',
        'family': 'Action, Combat & Pursuit',
        'directive': 'PLAY STYLE — SIEGE DEFENSE / LAST STAND: Dwell on fortifications, waves, breaches, triage, dwindling ammo or spells, morale, sacrifices, and the moment the line almost breaks. Compress offstage politics and travel. Let tension build as attrition ratchet with breach spikes. Make victory mean hold until relief, evacuation, dawn, or mission completion; make loss come from the line breaks, morale collapses, the protected thing falls, or the defenders are overwhelmed.',
    },
    'chase_pursuit': {
        'name': 'Chase / Pursuit',
        'family': 'Action, Combat & Pursuit',
        'directive': 'PLAY STYLE — CHASE / PURSUIT: Dwell on routes, chokepoints, vehicles or footwork, near misses, exhaustion, the shrinking gap, and sudden reversals. Compress leisure, safety, and anything not motion or evasion. Let tension build as sustained pressure with closing spikes. Make victory mean shake the pursuer, catch the target, reach sanctuary, or turn the tables; make loss come from be run down, lose the quarry, hit a dead end, or exhaust your margin.',
    },
    'vehicle_combat': {
        'name': 'Vehicle Combat',
        'family': 'Action, Combat & Pursuit',
        'directive': 'PLAY STYLE — VEHICLE COMBAT: Dwell on speed, range, arcs, maneuvers, collisions, damage control, crew roles, terrain, and the vehicle as body. Compress static tactical detail and personal drama unrelated to the machine. Let tension build as kinetic oscillation — momentum, damage, and position trade rapidly. Make victory mean disable, outrun, board, destroy, or escape the opposing vehicle; make loss come from lose control, suffer critical damage, crash, or get boxed in.',
    },
    'battle_royale': {
        'name': 'Battle Royale',
        'family': 'Action, Combat & Pursuit',
        'directive': 'PLAY STYLE — BATTLE ROYALE: Dwell on arena geography, scarcity drops, temporary alliances, betrayals, ambushes, zone pressure, and the final narrowing. Compress long backstory and fair fights without survival logic. Let tension build as contraction ratchet — space and options shrink. Make victory mean be the last survivor or extract under the contest’s victory rule; make loss come from be eliminated, trapped by the zone, betrayed, or exhausted by bad engagements.',
    },
    'wilderness_survival': {
        'name': 'Wilderness Survival',
        'family': 'Survival, Scarcity & Endurance',
        'directive': 'PLAY STYLE — WILDERNESS SURVIVAL: Dwell on hunger, thirst, cold, injury, exhaustion, weather, terrain, rationing, and small victories like fire or water. Compress rich plotting, social intrigue, fast travel, and convenient rescue. Let tension build as grind/attrition with acute crises. Make victory mean reach safety, get rescued, or endure until conditions break; make loss come from die of exposure, starvation, dehydration, injury, or exhaustion.',
    },
    'disaster_escape': {
        'name': 'Disaster / Escape',
        'family': 'Survival, Scarcity & Endurance',
        'directive': 'PLAY STYLE — DISASTER / ESCAPE: Dwell on spreading danger, collapsing routes, smoke, water, fire, contagion, split-second choices, and rescue tradeoffs. Compress backstory and anything not bearing on escape. Let tension build as accelerating ratchet against a hard clock. Make victory mean reach safety before collapse completes, ideally with those chosen to save; make loss come from be trapped, cut off, consumed, or too late.',
    },
    'post_collapse_scavenging': {
        'name': 'Post-Collapse Scavenging',
        'family': 'Survival, Scarcity & Endurance',
        'directive': 'PLAY STYLE — POST-COLLAPSE SCAVENGING: Dwell on empty stores, dangerous ruins, hunger, barter, distrust, improvised repair, moral compromises, and scarcity arithmetic. Compress pre-collapse exposition and easy abundance. Let tension build as attrition punctuated by haul spikes. Make victory mean secure enough supplies, route, or refuge to survive the next horizon; make loss come from starve, attract raiders, exhaust supplies, or lose the group’s trust.',
    },
    'base_survival': {
        'name': 'Base Survival',
        'family': 'Survival, Scarcity & Endurance',
        'directive': 'PLAY STYLE — BASE SURVIVAL: Dwell on walls, farms, generators, watch rotations, repair, ration stores, morale, and attacks that reveal weak points. Compress adventures that do not affect the base. Let tension build as compound-and-stress — improvement followed by shocks. Make victory mean keep the base functioning and protected through the crisis; make loss come from breach, starvation, disease, collapse, mutiny, or abandonment.',
    },
    'plague_containment': {
        'name': 'Plague / Containment',
        'family': 'Survival, Scarcity & Endurance',
        'directive': 'PLAY STYLE — PLAGUE / CONTAINMENT: Dwell on symptoms, contact tracing, quarantine, public fear, medical uncertainty, scarce supplies, and ethical containment choices. Compress generic monster fighting and unrelated politics. Let tension build as exponential dread — delay makes every later choice harder. Make victory mean contain, cure, slow, or survive the outbreak with society intact enough; make loss come from spread escapes control, trust collapses, cure fails, or containment becomes atrocity.',
    },
    'medical_triage_survival': {
        'name': 'Medical Triage Survival',
        'family': 'Survival, Scarcity & Endurance',
        'directive': 'PLAY STYLE — MEDICAL TRIAGE SURVIVAL: Dwell on vitals, wounds, limited supplies, triage tags, exhaustion, who gets care, and the emotional cost of choosing. Compress heroic cures without tradeoff and unrelated hospital drama. Let tension build as pressure bursts — each influx forces new prioritization. Make victory mean save the most lives or the right lives by the mission’s values; make loss come from resources are wasted, preventable deaths cascade, or the healer breaks.',
    },
    'extreme_environment_trek': {
        'name': 'Extreme Environment Trek',
        'family': 'Survival, Scarcity & Endurance',
        'directive': 'PLAY STYLE — EXTREME ENVIRONMENT TREK: Dwell on oxygen, pressure, heat, cold, radiation, suit integrity, navigation, fatigue, and awe at lethal scale. Compress ordinary travel and casual survival shortcuts. Let tension build as attrition corridor — safety margins narrow with distance. Make victory mean cross, return, or reach the objective before margins fail; make loss come from equipment failure, wrong route, exposure, or losing the weather window.',
    },
    'moral_lifeboat': {
        'name': 'Moral Lifeboat',
        'family': 'Survival, Scarcity & Endurance',
        'directive': 'PLAY STYLE — MORAL LIFEBOAT: Dwell on who eats, who waits, who risks, leadership legitimacy, resentment, sacrifice, and the group’s changing moral line. Compress simple villainy and easy third options. Let tension build as ethical attrition — scarcity turns values into decisions. Make victory mean preserve life and a defensible moral community; make loss come from survive as monsters, collapse into violence, or choose a line you cannot live with.',
    },
    'injury_recovery': {
        'name': 'Injury Recovery',
        'family': 'Survival, Scarcity & Endurance',
        'directive': 'PLAY STYLE — INJURY RECOVERY: Dwell on pain, blood loss, mobility, infection, improvised care, dependence, pride, and the frustration of reduced agency. Compress heroic action that ignores injury and instant recovery. Let tension build as bodily attrition — the wound narrows choices until treated or escaped. Make victory mean stabilize, reach help, or complete the essential task despite impairment; make loss come from collapse, infection, shock, dependency exploited, or overexertion worsening the injury.',
    },
    'exploration_discovery': {
        'name': 'Exploration / Discovery',
        'family': 'Exploration, Wonder & Place',
        'directive': 'PLAY STYLE — EXPLORATION / DISCOVERY: Dwell on new vistas, strangeness, navigation, orientation, hazard, map-filling, awe, and unease. Compress repetitive charted travel, bookkeeping, and combat unless place demands it. Let tension build as slow warming with discovery spikes. Make victory mean reach, chart, recover, or return with knowledge from the unknown; make loss come from get lost, stranded, claimed by the frontier, or fail to return.',
    },
    'dungeon_delve': {
        'name': 'Dungeon Delve',
        'family': 'Exploration, Wonder & Place',
        'directive': 'PLAY STYLE — DUNGEON DELVE: Dwell on distinct rooms, threats, treasure, light, spells, HP, supplies, traps, and push-your-luck retreat choices. Compress the world above, travel to entrance, and downtime. Let tension build as risk/reward ratchet — danger and payoff rise while resources fall. Make victory mean reach the bottom, claim the prize, and get out with the haul; make loss come from die deep, overextend, or lose everything gathered.',
    },
    'derelict_ruin_exploration': {
        'name': 'Derelict / Ruin Exploration',
        'family': 'Exploration, Wonder & Place',
        'directive': 'PLAY STYLE — DERELICT / RUIN EXPLORATION: Dwell on objects, layout, remains, records, absence, mood, small revelations, and recontextualized rooms. Compress live antagonists, resource grind, and logistics. Let tension build as slow warming through dawning comprehension. Make victory mean understand what happened and reach the heart of the place; make loss come from leave without understanding or let the past reach forward and undo you.',
    },
    'lost_world_expedition': {
        'name': 'Lost World Expedition',
        'family': 'Exploration, Wonder & Place',
        'directive': 'PLAY STYLE — LOST WORLD EXPEDITION: Dwell on first vistas, unknown species, customs, expedition politics, ecological rules, and the danger of contamination or exploitation. Compress routine travel before discovery. Let tension build as discovery arc with escalating ethical stakes. Make victory mean document, survive, protect, or return from the lost place with understanding; make loss come from exploit or destroy it, become trapped, or misread its dangers.',
    },
    'road_trip': {
        'name': 'Road Trip',
        'family': 'Exploration, Wonder & Place',
        'directive': 'PLAY STYLE — ROAD TRIP: Dwell on roadside encounters, vehicle or route intimacy, detours, conversations, music, changing landscapes, and recurring tensions. Compress destination logistics and high plot when it ignores the journey. Let tension build as episodic warming — stops spike and travel lets consequences breathe. Make victory mean arrive changed, reconciled, or clarified by the journey; make loss come from arrive unchanged, break the bond, lose the route, or abandon the reason for travel.',
    },
    'pilgrimage': {
        'name': 'Pilgrimage',
        'family': 'Exploration, Wonder & Place',
        'directive': 'PLAY STYLE — PILGRIMAGE: Dwell on ritual stops, vows, temptations, companions, hardship, signs, doubt, and the changing meaning of the destination. Compress tourist logistics and unrelated combat. Let tension build as slow spiritual ratchet — external distance becomes inner pressure. Make victory mean reach the destination transformed, absolved, or truthfully changed; make loss come from turn back empty, break the vow, reach the place unchanged, or reject the wrong lesson.',
    },
    'urban_sandbox': {
        'name': 'Urban Sandbox',
        'family': 'Exploration, Wonder & Place',
        'directive': 'PLAY STYLE — URBAN SANDBOX: Dwell on neighborhood texture, rumors, landmarks, social geography, hidden doors, faction territories, and recurring local consequences. Compress empty streets and travel between known hubs. Let tension build as open-web accretion — discoveries thicken the city map. Make victory mean gain a place, solve local goals, or master the city’s networks; make loss come from get isolated, blacklisted, lost in noise, or trigger hostile attention.',
    },
    'first_contact': {
        'name': 'First Contact',
        'family': 'Exploration, Wonder & Place',
        'directive': 'PLAY STYLE — FIRST CONTACT: Dwell on misread signals, cautious gestures, protocol, taboo, translation, mutual fear, and first shared concepts. Compress combat unless diplomacy has failed and routine travel. Let tension build as delicate warming with misunderstanding spikes. Make victory mean achieve mutual comprehension, peace, exchange, or safe separation; make loss come from cause panic, contamination, war, insult, or irreversible misunderstanding.',
    },
    'cultural_immersion': {
        'name': 'Cultural Immersion',
        'family': 'Exploration, Wonder & Place',
        'directive': 'PLAY STYLE — CULTURAL IMMERSION: Dwell on rituals, meals, dress, greetings, shame, humor, taboos, local categories, and mistakes that teach. Compress tourist summary and outsider superiority. Let tension build as slow attunement — confusion becomes fluency. Make victory mean earn trust and function within the culture without erasing it; make loss come from offend, misread, appropriate, or remain permanently outside.',
    },
    'planetary_survey': {
        'name': 'Planetary Survey',
        'family': 'Exploration, Wonder & Place',
        'directive': 'PLAY STYLE — PLANETARY SURVEY: Dwell on sensor passes, specimen notes, weather, hazards, ecological relationships, landing sites, and competing survey priorities. Compress political plot and combat except as environmental consequence. Let tension build as methodical discovery with anomaly spikes. Make victory mean produce a reliable survey and decide safe use, protection, or evacuation; make loss come from miss a hazard, contaminate data, misclassify life, or greenlight disaster.',
    },
    'romance': {
        'name': 'Romance',
        'family': 'Social, Relationship & Intimacy',
        'directive': 'PLAY STYLE — ROMANCE: Dwell on charged moments, subtext, vulnerability, approach and retreat, obstacles, refusals, and growing intimacy. Compress unrelated plot machinery and time outside their orbit. Let tension build as slow warming with charged spikes and reversals. Make victory mean mutual connection is secured, consummated, or chosen with agency; make loss come from rejection, withering, dishonesty, or obstacle ending the bond.',
    },
    'social_drama_relationship_web': {
        'name': 'Social Drama / Relationship Web',
        'family': 'Social, Relationship & Intimacy',
        'directive': 'PLAY STYLE — SOCIAL DRAMA / RELATIONSHIP WEB: Dwell on conversation subtext, jealousy, secrets, alliances, betrayals, confidences, and consequences spreading through the web. Compress physical action, solitary activity, and external plot that does not affect relationships. Let tension build as accretion with revelation spikes. Make victory mean land the relational outcome, protect or expose the right secret, or hold the group together; make loss come from the web turns on you, relationships collapse, or exposure ruins needed bonds.',
    },
    'slice_of_life_cozy': {
        'name': 'Slice of Life / Cozy',
        'family': 'Social, Relationship & Intimacy',
        'directive': 'PLAY STYLE — SLICE OF LIFE / COZY: Dwell on routine, small pleasures, chores, seasons, warm interactions, gradual improvements, and comfort accruing. Compress mortal danger, urgency, and grand plot. Let tension build as gentle warming with seasonal rhythms. Make victory mean a flourishing life, tended place, or deepened bond; make loss come from stagnation, neglect, decay of what was built, or soft relational loss.',
    },
    'found_family_crew_bonding': {
        'name': 'Found Family / Crew Bonding',
        'family': 'Social, Relationship & Intimacy',
        'directive': 'PLAY STYLE — FOUND FAMILY / CREW BONDING: Dwell on campfire scenes, private favors, inside jokes, loyalty tests, conflict repair, shared rituals, and sacrifices for the group. Compress plot beats that do not change the bond. Let tension build as warm accretion with betrayal or sacrifice spikes. Make victory mean the group becomes loyal, resilient, and chosen; make loss come from the crew fractures, a betrayal sticks, or members remain merely functional strangers.',
    },
    'family_saga': {
        'name': 'Family Saga',
        'family': 'Social, Relationship & Intimacy',
        'directive': 'PLAY STYLE — FAMILY SAGA: Dwell on family rituals, old grievances, lineage, property, caregiving, sibling rivalry, marriages, and inherited obligations. Compress outside plot not connected to family consequence. Let tension build as generational accretion — old choices echo into new scenes. Make victory mean reconcile, preserve, transform, or truthfully leave the family system; make loss come from repeat the harm, lose the inheritance or bond, or let secrets poison the line.',
    },
    'mentorship_apprenticeship': {
        'name': 'Mentorship / Apprenticeship',
        'family': 'Social, Relationship & Intimacy',
        'directive': 'PLAY STYLE — MENTORSHIP / APPRENTICESHIP: Dwell on practice, critique, demonstrations, failures, resentment, breakthrough, tradition, and the moment the student exceeds the lesson. Compress unrelated adventures and instant mastery. Let tension build as training arc — repetition becomes transformation. Make victory mean the learner becomes capable and the relationship matures or releases; make loss come from the lesson fails, pride blocks growth, the mentor exploits, or dependence persists.',
    },
    'rivalry': {
        'name': 'Rivalry',
        'family': 'Social, Relationship & Intimacy',
        'directive': 'PLAY STYLE — RIVALRY: Dwell on recurring encounters, mirrored goals, taunts, mutual respect, jealousy, escalation, and personal stakes in winning. Compress faceless competition and one-off enemies. Let tension build as episodic escalation — each meeting redefines the rivalry. Make victory mean surpass, reconcile with, or decisively define yourself against the rival; make loss come from become consumed, outgrown, humiliated, or refuse the growth the rivalry offered.',
    },
    'reconciliation': {
        'name': 'Reconciliation',
        'family': 'Social, Relationship & Intimacy',
        'directive': 'PLAY STYLE — RECONCILIATION: Dwell on apology, memory, harm named plainly, defensive reactions, restitution, time, and proof through action. Compress quick forgiveness and external plot that dodges responsibility. Let tension build as slow thaw with relapse spikes. Make victory mean earn renewed trust or a truthful peaceful separation; make loss come from performative apology, refusal to change, reopening harm, or rejection you must accept.',
    },
    'negotiation_debate': {
        'name': 'Negotiation / Debate',
        'family': 'Social, Relationship & Intimacy',
        'directive': 'PLAY STYLE — NEGOTIATION / DEBATE: Dwell on offers, counteroffers, arguments, tells, concessions, bluffs, walk-away points, rules, and advantage shifts. Compress physical action, world outside the room, and fact discovery except as deployed evidence. Let tension build as exchange accretion with reversals. Make victory mean secure the deal, verdict, concession, or agreement on your terms; make loss come from talks collapse, you are out-leveraged, or the other side walks or wins the room.',
    },
    'therapy_confession': {
        'name': 'Therapy / Confession',
        'family': 'Social, Relationship & Intimacy',
        'directive': 'PLAY STYLE — THERAPY / CONFESSION: Dwell on silences, evasions, memories, body language, trust, reframing, resistance, and the fragile moment of admission. Compress external adventure and coercive interrogation. Let tension build as delicate accretion — safety deepens until truth can surface. Make victory mean the person names the truth and chooses a healthier next step; make loss come from trust breaks, harm is mishandled, or the confession becomes exploitation.',
    },
    'community_healing': {
        'name': 'Community Healing',
        'family': 'Social, Relationship & Intimacy',
        'directive': 'PLAY STYLE — COMMUNITY HEALING: Dwell on neighbors, old grievances, public rituals, repairs, shared meals, apologies, memorials, and visible signs of trust returning. Compress external villain plots that do not touch the community wound. Let tension build as gentle accretion with relapse spikes. Make victory mean restore enough trust and function for the community to flourish; make loss come from paper over harm, choose favorites, let resentment harden, or rebuild structures without belonging.',
    },
    'sanctuary_keeper': {
        'name': 'Sanctuary Keeper',
        'family': 'Social, Relationship & Intimacy',
        'directive': 'PLAY STYLE — SANCTUARY KEEPER: Dwell on beds, meals, entry rules, hidden rooms, guest stories, threats at the door, scarce comfort, and who is allowed in. Compress adventures that abandon the sanctuary’s duty. Let tension build as care pressure — safety is maintained through repeated small decisions and occasional breaches. Make victory mean keep the sanctuary safe, trusted, and morally coherent; make loss come from betray a guest, admit danger blindly, run out of care, or let fear close the door.',
    },
    'political_intrigue': {
        'name': 'Political Intrigue',
        'family': 'Politics, Factions & Institutions',
        'directive': 'PLAY STYLE — POLITICAL INTRIGUE: Dwell on factions, public words, private bargains, favors owed, blackmail, shifting support, and betrayal at pivots. Compress physical action, travel, and the world outside the arena except as leverage. Let tension build as accretion with reversals. Make victory mean secure and hold the contested position or policy; make loss come from be outmaneuvered, exiled, stripped, married off, ruined, or killed.',
    },
    'faction_politics': {
        'name': 'Faction Politics',
        'family': 'Politics, Factions & Institutions',
        'directive': 'PLAY STYLE — FACTION POLITICS: Dwell on faction goals, territory, symbols, old wounds, alliance math, reputation shifts, and the cost of pleasing one group. Compress individual drama that does not affect faction standing. Let tension build as web accretion — every favor tilts the board. Make victory mean achieve the objective while keeping enough faction support or neutrality; make loss come from unite factions against you, trigger war, or lose all legitimacy.',
    },
    'rebellion_resistance': {
        'name': 'Rebellion / Resistance',
        'family': 'Politics, Factions & Institutions',
        'directive': 'PLAY STYLE — REBELLION / RESISTANCE: Dwell on safehouses, cells, coded trust, propaganda, raids, martyrdom, informers, and the dilemma of violent means. Compress open warfare too early and grand speeches without infrastructure. Let tension build as underground ratchet — capability and repression grow together. Make victory mean weaken the regime, protect the movement, and spark durable change; make loss come from the cell is rolled up, morally discredited, infiltrated, or crushed before support grows.',
    },
    'revolution': {
        'name': 'Revolution',
        'family': 'Politics, Factions & Institutions',
        'directive': 'PLAY STYLE — REVOLUTION: Dwell on crowds, slogans, crackdowns, councils, faction splits, purges, compromises, and the gap between dream and governance. Compress single-hero solutions and purely private stakes. Let tension build as escalating wave with aftermath inversion. Make victory mean topple or transform the order and build something that can live; make loss come from counterrevolution, civil war, betrayal of ideals, or replacing tyranny with another.',
    },
    'kingdom_state_rule': {
        'name': 'Kingdom / State Rule',
        'family': 'Politics, Factions & Institutions',
        'directive': 'PLAY STYLE — KINGDOM / STATE RULE: Dwell on petitions, budgets, famine, courts, borders, nobles, public trust, edicts, and consequences of policy. Compress individual errands and tactical detail beneath the scale. Let tension build as compound-and-crisis — decisions accumulate until shocks reveal them. Make victory mean a stable, legitimate realm that survives crises and expresses chosen values; make loss come from rebellion, bankruptcy, invasion, famine, succession failure, or legitimacy collapse.',
    },
    'election_council_game': {
        'name': 'Election / Council Game',
        'family': 'Politics, Factions & Institutions',
        'directive': 'PLAY STYLE — ELECTION / COUNCIL GAME: Dwell on vote math, blocs, endorsements, speeches, scandals, procedural rules, polling, and last-minute flips. Compress violence and policy implementation after the vote unless it affects support. Let tension build as countdown ratchet toward decision day. Make victory mean win the vote, seat, motion, or mandate with legitimacy intact; make loss come from lose the count, win illegitimately, suffer scandal collapse, or fracture coalition.',
    },
    'diplomatic_summit_peace_process': {
        'name': 'Diplomatic Summit / Peace Process',
        'family': 'Politics, Factions & Institutions',
        'directive': 'PLAY STYLE — DIPLOMATIC SUMMIT / PEACE PROCESS: Dwell on protocol, seating, interpreters, face-saving, concessions, red lines, backchannels, and spoilers trying to break trust. Compress combat and domestic detail beyond negotiating leverage. Let tension build as fragile accretion with crisis spikes. Make victory mean secure treaty, truce, recognition, exchange, or peaceful exit; make loss come from walkout, insult, assassination, mistranslation, or renewed conflict.',
    },
    'survival_horror': {
        'name': 'Survival Horror',
        'family': 'Horror, Dread & the Uncanny',
        'directive': 'PLAY STYLE — SURVIVAL HORROR: Dwell on vulnerability, light, ammo, healing, safe rooms, monster proximity, hiding, and choosing whether to spend resources. Compress power fantasy, easy victory, comfort, and tactical mastery. Let tension build as oppressive grind with terror spikes. Make victory mean survive the night, escape the place, or evade the threat with scraps left; make loss come from caught, cornered, depleted, or forced into a fight you cannot win.',
    },
    'cosmic_sanity_horror': {
        'name': 'Cosmic / Sanity Horror',
        'family': 'Horror, Dread & the Uncanny',
        'directive': 'PLAY STYLE — COSMIC / SANITY HORROR: Dwell on wrongness, vast indifference, fragmentary revelation, sanity erosion, human smallness, and dread that knowledge worsens. Compress clean victory, conventional combat, and tidy explanation. Let tension build as downward spiral — knowledge increases danger and instability. Make victory mean forestall, contain, or survive with self mostly intact, often pyrrhically; make loss come from madness, consumption, completing the thing you opposed, or understanding too much.',
    },
    'psychological_dread_horror': {
        'name': 'Psychological / Dread Horror',
        'family': 'Horror, Dread & the Uncanny',
        'directive': 'PLAY STYLE — PSYCHOLOGICAL / DREAD HORROR: Dwell on atmosphere, unreliable perception, isolation, repeated motifs, intimacy of threat, and erosion of certainty. Compress clear monsters, reassuring explanation, and resource accounting. Let tension build as slow warming dread with destabilizing reversals. Make victory mean endure, escape, or resolve the wrongness with self intact; make loss come from succumb to the thing, madness, guilt, or self-unraveling.',
    },
    'haunted_house': {
        'name': 'Haunted House',
        'family': 'Horror, Dread & the Uncanny',
        'directive': 'PLAY STYLE — HAUNTED HOUSE: Dwell on rooms as memory, apparitions, cold spots, repeated scenes, objects out of place, history, and appeasement clues. Compress generic monster fights and leaving trivially. Let tension build as spatial dread — deeper rooms reveal older wounds. Make victory mean understand, appease, cleanse, escape, or survive the house’s truth; make loss come from be trapped, possessed by the past, or repeat the old harm.',
    },
    'possession_exorcism': {
        'name': 'Possession / Exorcism',
        'family': 'Horror, Dread & the Uncanny',
        'directive': 'PLAY STYLE — POSSESSION / EXORCISM: Dwell on changes in voice, taboo names, sacred tools, host vulnerability, ritual steps, faith, doubt, and backlash. Compress simple combat and medical routine after possession is proven. Let tension build as ritual ratchet — preparation narrows to a dangerous confrontation. Make victory mean free the host with body and soul intact; make loss come from kill the host, empower the entity, fail the rite, or lose faith at the critical moment.',
    },
    'creature_feature': {
        'name': 'Creature Feature',
        'family': 'Horror, Dread & the Uncanny',
        'directive': 'PLAY STYLE — CREATURE FEATURE: Dwell on tracks, kills, lair, appetite, movement, biology, false safety, and confrontations shaped by the creature’s nature. Compress abstract evil and human politics not tied to the beast. Let tension build as stalk-and-eruption — quiet signs, sudden attacks. Make victory mean escape, trap, kill, or redirect the creature; make loss come from be eaten, misread its rules, enter its territory wrongly, or lure it to victims.',
    },
    'folk_horror_community': {
        'name': 'Folk Horror Community',
        'family': 'Horror, Dread & the Uncanny',
        'directive': 'PLAY STYLE — FOLK HORROR COMMUNITY: Dwell on hospitality, festivals, taboos, local songs, social pressure, old bargains, outsider confusion, and communal complicity. Compress urban safety nets and lone monster logic. Let tension build as pastoral unease tightening into ritual inevitability. Make victory mean escape, expose, break, or survive the communal ritual; make loss come from be assimilated, sacrificed, silenced, or convinced the horror is normal.',
    },
    'cursed_object': {
        'name': 'Cursed Object',
        'family': 'Horror, Dread & the Uncanny',
        'directive': 'PLAY STYLE — CURSED OBJECT: Dwell on rules, prior owners, bargains, temptation, symptoms, loopholes, failed disposals, and the price of each use. Compress generic haunting not tied to the object. Let tension build as rule accretion with temptation spikes. Make victory mean break, contain, safely pass, or survive the curse without unacceptable cost; make loss come from misuse it, pass harm onward, trigger the final price, or become attached to power.',
    },
    'body_horror_transformation': {
        'name': 'Body Horror Transformation',
        'family': 'Horror, Dread & the Uncanny',
        'directive': 'PLAY STYLE — BODY HORROR TRANSFORMATION: Dwell on sensory disgust, medical details, shame, appetite, mirrors, concealment, changing abilities, and identity erosion. Compress external threat that ignores embodiment. Let tension build as intimate escalation — each change makes selfhood less stable. Make victory mean halt, integrate, cure, or choose the transformation knowingly; make loss come from lose bodily autonomy, infect others, deny too long, or become unrecognizable.',
    },
    'paranoia_horror': {
        'name': 'Paranoia Horror',
        'family': 'Horror, Dread & the Uncanny',
        'directive': 'PLAY STYLE — PARANOIA HORROR: Dwell on accusations, tests, false positives, isolation, group fracture, signs of contamination, and fear of sleep or privacy. Compress clear proof too early and lone survival unrelated to trust. Let tension build as contracting circle — suspicion consumes the group. Make victory mean identify the threat or preserve enough trust to survive uncertainty; make loss come from kill innocents, trust the wrong person, fracture beyond recovery, or become the threat.',
    },
    'temptation_corruption_horror': {
        'name': 'Temptation / Corruption Horror',
        'family': 'Horror, Dread & the Uncanny',
        'directive': 'PLAY STYLE — TEMPTATION / CORRUPTION HORROR: Dwell on tempting benefits, rationalizations, small first steps, escalating costs, secrecy, bodily or social marks, and moments of refusal. Compress external monsters unrelated to the temptation. Let tension build as downward seduction — each use makes the next easier and costlier. Make victory mean refuse, contain, confess, or pay a chosen cost before identity is remade; make loss come from succumb, harm others, normalize the corruption, or become the thing once feared.',
    },
    'stewardship_management': {
        'name': 'Stewardship / Management',
        'family': 'Stewardship, Building & Management',
        'directive': 'PLAY STYLE — STEWARDSHIP / MANAGEMENT: Dwell on growth, resource flows, bottlenecks, tradeoffs, structural decisions, dashboards, and stress-test crises. Compress granular action and personal scenes that do not affect the system. Let tension build as accretion with stress tests. Make victory mean a thriving, resilient system at scale; make loss come from collapse, bankruptcy, breakdown, or failure under load.',
    },
    'settlement_builder': {
        'name': 'Settlement Builder',
        'family': 'Stewardship, Building & Management',
        'directive': 'PLAY STYLE — SETTLEMENT BUILDER: Dwell on layouts, first buildings, supply lines, disputes, festivals, defenses, public works, and visible growth. Compress single-adventurer heroics outside settlement needs. Let tension build as seasonal compound growth with crisis spikes. Make victory mean a stable, loved, defensible settlement; make loss come from starvation, abandonment, raid, fire, faction split, or failure to become a community.',
    },
    'colony_simulator': {
        'name': 'Colony Simulator',
        'family': 'Stewardship, Building & Management',
        'directive': 'PLAY STYLE — COLONY SIMULATOR: Dwell on work schedules, moods, injuries, shortages, breakdowns, personality clashes, and emergent stories from systems. Compress hand-authored plot that overrides simulation. Let tension build as systems attrition with emergent spikes. Make victory mean the colony becomes self-sustaining and socially durable; make loss come from cascade failure from hunger, madness, conflict, weather, or bad planning.',
    },
    'farm_homestead': {
        'name': 'Farm / Homestead',
        'family': 'Stewardship, Building & Management',
        'directive': 'PLAY STYLE — FARM / HOMESTEAD: Dwell on planting, weather, chores, animals, harvests, upgrades, neighbors, and rituals of place. Compress high-stakes combat and distant plot. Let tension build as seasonal cycle — effort returns later. Make victory mean a flourishing homestead and rooted life; make loss come from neglect, failed harvest, debt, isolation, or loss of land.',
    },
    'business_tycoon': {
        'name': 'Business / Tycoon',
        'family': 'Stewardship, Building & Management',
        'directive': 'PLAY STYLE — BUSINESS / TYCOON: Dwell on cashflow, inventory, customers, staffing, competition, expansion, debt, and strategic tradeoffs. Compress personal scenes unrelated to operations. Let tension build as growth curve with market shocks. Make victory mean a profitable, resilient, reputable enterprise; make loss come from bankruptcy, scandal, supply failure, debt spiral, or customer collapse.',
    },
    'tavern_social_hub': {
        'name': 'Tavern / Social Hub',
        'family': 'Stewardship, Building & Management',
        'directive': 'PLAY STYLE — TAVERN / SOCIAL HUB: Dwell on regulars, menus, staff, rushes, overheard secrets, hospitality, decor, and the tavern as community center. Compress distant adventure unless it enters through guests. Let tension build as cozy operational rhythm with rumor spikes. Make victory mean a beloved, solvent hub full of returning people and useful stories; make loss come from bad service, debt, violence, scandal, or losing the trust of regulars.',
    },
    'workshop_crafting': {
        'name': 'Workshop / Crafting',
        'family': 'Stewardship, Building & Management',
        'directive': 'PLAY STYLE — WORKSHOP / CRAFTING: Dwell on material qualities, tools, recipes, failures, client requests, upgrades, and satisfaction of a made object. Compress combat or travel unless it affects materials. Let tension build as incremental mastery — better inputs and skill unlock better outputs. Make victory mean create the needed item, master the craft, or sustain the workshop; make loss come from waste rare materials, fail commissions, stagnate, or craft something dangerous badly.',
    },
    'trade_logistics': {
        'name': 'Trade / Logistics',
        'family': 'Stewardship, Building & Management',
        'directive': 'PLAY STYLE — TRADE / LOGISTICS: Dwell on routes, cargo priorities, capacity, delays, tariffs, spoilage, weather, escorts, warehouses, and bottleneck relief. Compress personal heroics not affecting flow. Let tension build as network pressure — delays cascade through the map. Make victory mean deliver reliably and profitably or keep the network alive; make loss come from miss deadlines, lose cargo, trigger shortages, or bankrupt the route.',
    },
    'fashion_makeover': {
        'name': 'Fashion / Makeover',
        'family': 'Creativity, Craft & Performance',
        'directive': 'PLAY STYLE — FASHION / MAKEOVER: Dwell on fabric, silhouette, taste, constraints, social codes, reveal moments, self-image, and audience reaction. Compress combat and plot that ignores presentation. Let tension build as preparation to reveal — tension lands when the look enters the room. Make victory mean achieve the intended impression, transformation, or self-expression; make loss come from misread the code, feel false, offend the room, or fail the reveal.',
    },
    'interior_space_design': {
        'name': 'Interior / Space Design',
        'family': 'Creativity, Craft & Performance',
        'directive': 'PLAY STYLE — INTERIOR / SPACE DESIGN: Dwell on layout, light, texture, furniture, constraints, before-and-after reveals, and how people move in the space. Compress external adventure and technical detail that does not change design choice. Let tension build as iterative refinement with reveal payoff. Make victory mean create a space that serves its purpose and feels right; make loss come from clutter, mismatch, poor function, rejected taste, or space that produces wrong behavior.',
    },
    'music_rhythm_performance': {
        'name': 'Music / Rhythm Performance',
        'family': 'Creativity, Craft & Performance',
        'directive': 'PLAY STYLE — MUSIC / RHYTHM PERFORMANCE: Dwell on rehearsal, timing, mistakes, ensemble listening, tempo, audience, emotional interpretation, and the performance moment. Compress plot logistics and nonmusical conflict unrelated to the piece. Let tension build as build-and-release — practice narrows into performance. Make victory mean deliver the performance, win connection, or express the truth through music; make loss come from lose timing, freeze, alienate the audience, or fail to listen.',
    },
    'theater_stage_show': {
        'name': 'Theater / Stage Show',
        'family': 'Creativity, Craft & Performance',
        'directive': 'PLAY STYLE — THEATER / STAGE SHOW: Dwell on rehearsal rooms, blocking, missed cues, backstage stress, actor conflicts, improvisation, and curtain-up pressure. Compress the world outside production unless it threatens the show. Let tension build as countdown to live reveal with crisis spikes. Make victory mean the show lands before the audience despite everything; make loss come from the production collapses, truth breaks badly, or the audience is lost.',
    },
    'cooking_contest': {
        'name': 'Cooking Contest',
        'family': 'Creativity, Craft & Performance',
        'directive': 'PLAY STYLE — COOKING CONTEST: Dwell on ingredients, prep, heat, timing, mistakes, aroma, taste memory, plating, judging criteria, and rival dishes. Compress unrelated drama outside kitchen. Let tension build as clocked craft ratchet. Make victory mean serve a dish that meets the challenge and moves the judge or guest; make loss come from burn, undercook, misread the prompt, run out of time, or produce food without meaning.',
    },
    'art_authorship': {
        'name': 'Art / Authorship',
        'family': 'Creativity, Craft & Performance',
        'directive': 'PLAY STYLE — ART / AUTHORSHIP: Dwell on drafts, sketches, blocks, choices of form, critique, patrons, audience interpretation, and the artist’s changing intent. Compress action unrelated to the work. Let tension build as slow refinement with reception spike. Make victory mean complete a work that expresses or accomplishes what matters; make loss come from abandon it, sell it hollow, be misunderstood fatally, or lose the voice.',
    },
    'medical_procedural': {
        'name': 'Medical Procedural',
        'family': 'Professional & Procedural Competence',
        'directive': 'PLAY STYLE — MEDICAL PROCEDURAL: Dwell on symptoms, tests, differential diagnosis, consent, vitals, team roles, complications, and bedside judgment. Compress miracle cures and unrelated romance unless it affects care. Let tension build as procedural clock — body time narrows options. Make victory mean stabilize, cure, or make the best defensible medical call; make loss come from misdiagnose, delay, violate trust, or lose the patient preventably.',
    },
    'legal_trial': {
        'name': 'Legal Trial',
        'family': 'Professional & Procedural Competence',
        'directive': 'PLAY STYLE — LEGAL TRIAL: Dwell on witness prep, cross-examination, exhibits, objections, burden of proof, jury perception, and legal strategy. Compress detective legwork once evidence is already in hand. Let tension build as adversarial accretion with reversal moments. Make victory mean win verdict, settlement, injunction, or legal protection; make loss come from lose the ruling, overreach, get evidence excluded, or betray the client’s interest.',
    },
    'emergency_dispatch': {
        'name': 'Emergency Dispatch',
        'family': 'Professional & Procedural Competence',
        'directive': 'PLAY STYLE — EMERGENCY DISPATCH: Dwell on caller panic, incomplete information, maps, unit availability, triage, scripts, and the burden of voice-only help. Compress on-scene heroics except through radio consequences. Let tension build as queue pressure — new calls reshape old priorities. Make victory mean route help effectively and keep people alive until responders arrive; make loss come from misprioritize, lose a caller, send wrong units, or overload the system.',
    },
    'fire_search_rescue': {
        'name': 'Fire / Search Rescue',
        'family': 'Professional & Procedural Competence',
        'directive': 'PLAY STYLE — FIRE / SEARCH RESCUE: Dwell on smoke, heat, rubble, maps, breathing gear, victim signals, team calls, and safety thresholds. Compress cause backstory and unrelated politics. Let tension build as hazard ratchet with oxygen or collapse clock. Make victory mean extract victims and crews before conditions fail; make loss come from victims lost, rescuers trapped, structure collapses, or safety line breaks.',
    },
    'academic_research': {
        'name': 'Academic Research',
        'family': 'Professional & Procedural Competence',
        'directive': 'PLAY STYLE — ACADEMIC RESEARCH: Dwell on hypotheses, fieldwork, archives, data mess, peer critique, funding, priority disputes, and intellectual humility. Compress action spectacle and instant genius. Let tension build as slow accretion with breakthrough and review spikes. Make victory mean produce a defensible contribution to knowledge; make loss come from fraud, bad data, scooping, rejection, or clinging to a false theory.',
    },
    'space_mission_control': {
        'name': 'Space Mission Control',
        'family': 'Professional & Procedural Competence',
        'directive': 'PLAY STYLE — SPACE MISSION CONTROL: Dwell on telemetry, checklists, calm voice loops, competing failure modes, simulations, crew trust, and time lag. Compress direct heroics and casual improvisation without procedure. Let tension build as procedural crisis ratchet. Make victory mean bring crew, craft, or mission through the failure state; make loss come from wrong call, lost signal, cascade failure, or sacrificing the wrong priority.',
    },
    'moral_dilemma_crucible': {
        'name': 'Moral Dilemma Crucible',
        'family': 'Moral, Psychological & Literary Drama',
        'directive': 'PLAY STYLE — MORAL DILEMMA CRUCIBLE: Dwell on values stated through action, tradeoffs, witnesses, irreversible choices, aftermath, and self-justification. Compress painless third options and villain caricatures. Let tension build as compressed ethical ratchet. Make victory mean make a choice you can defend and bear; make loss come from choose from fear, deny the cost, or destroy what you meant to preserve.',
    },
    'redemption_quest': {
        'name': 'Redemption Quest',
        'family': 'Moral, Psychological & Literary Drama',
        'directive': 'PLAY STYLE — REDEMPTION QUEST: Dwell on the named harm, victims’ agency, restitution, temptation to relapse, public versus private change, and sacrifice. Compress cheap forgiveness and unrelated adventure points. Let tension build as slow repair with temptation spikes. Make victory mean earn partial redemption or become worthy of forgiveness even if not granted; make loss come from repeat harm, demand forgiveness, hide truth, or choose image over repair.',
    },
    'tragedy_fall': {
        'name': 'Tragedy / Fall',
        'family': 'Moral, Psychological & Literary Drama',
        'directive': 'PLAY STYLE — TRAGEDY / FALL: Dwell on tempting choices, warnings ignored, pride, rationalization, narrowing exits, and recognition too late. Compress random misfortune detached from agency. Let tension build as downward ratchet — each choice makes the next fall easier. Make victory mean achieve tragic recognition, preserve one value, or avert the fall at real cost; make loss come from complete the fall blind, destroy others, or learn too late.',
    },
    'coming_of_age': {
        'name': 'Coming of Age',
        'family': 'Moral, Psychological & Literary Drama',
        'directive': 'PLAY STYLE — COMING OF AGE: Dwell on threshold experiences, mentors, peers, shame, first love or loss, rules questioned, and chosen values. Compress adult plot machinery not tied to growth. Let tension build as seasonal awakening with decisive thresholds. Make victory mean claim a more honest adult identity or chosen path; make loss come from remain defined by fear, imitation, or refusal of responsibility.',
    },
    'identity_exploration': {
        'name': 'Identity Exploration',
        'family': 'Moral, Psychological & Literary Drama',
        'directive': 'PLAY STYLE — IDENTITY EXPLORATION: Dwell on mirrors, names, pronouns or titles, masks, conflicting roles, community recognition, and choices that declare self. Compress external quests not pressuring identity. Let tension build as oscillation — identity claims are tested by situations. Make victory mean choose and inhabit an identity with agency and consequence; make loss come from let others define you, fragment, hide forever, or choose a false self to survive.',
    },
    'trauma_grief_recovery': {
        'name': 'Trauma / Grief Recovery',
        'family': 'Moral, Psychological & Literary Drama',
        'directive': 'PLAY STYLE — TRAUMA / GRIEF RECOVERY: Dwell on triggers, memories, rituals, support, numbness, anger, tenderness, setbacks, and small acts of living. Compress adventure that treats pain as solved by one victory. Let tension build as nonlinear thaw — progress and relapse coexist. Make victory mean integrate the loss and choose a livable future; make loss come from freeze, isolate, repeat harm, or mistake revenge for healing.',
    },
    'trial_of_faith': {
        'name': 'Trial of Faith',
        'family': 'Moral, Psychological & Literary Drama',
        'directive': 'PLAY STYLE — TRIAL OF FAITH: Dwell on ritual, doubt, counsel, signs, hypocrisy, sacrifice, unanswered prayer, and decisions made without certainty. Compress proof that removes the test and shallow sermonizing. Let tension build as spiritual pressure — silence and contradiction intensify. Make victory mean choose a truer relation to belief and act from it; make loss come from cling falsely, betray conscience, despair, or weaponize belief.',
    },
    'revenge_vs_mercy': {
        'name': 'Revenge vs. Mercy',
        'family': 'Moral, Psychological & Literary Drama',
        'directive': 'PLAY STYLE — REVENGE VS. MERCY: Dwell on memory of harm, target humanization, collateral damage, escalating methods, chances to stop, and aftermath. Compress simple monster targets with no moral pressure. Let tension build as hot pursuit cooling into moral reckoning. Make victory mean achieve justice without becoming ruled by vengeance, or consciously choose the cost; make loss come from kill the wrong self inside you, harm innocents, spare from cowardice, or avenge emptily.',
    },
    'farce_cover_up': {
        'name': 'Farce / Cover-Up',
        'family': 'Comedy, Farce & Chaos',
        'directive': 'PLAY STYLE — FARCE / COVER-UP: Dwell on bad timing, doors, overheard fragments, absurd alibis, prop misuse, escalating lies, and near exposure. Compress sober realism and consequences too heavy for play. Let tension build as comic ratchet — every fix creates two problems. Make victory mean get through the event with the secret intact or reveal it on your terms; make loss come from exposure at the worst moment, spiraling harm, or collapse of the lie machine.',
    },
    'mistaken_identity': {
        'name': 'Mistaken Identity',
        'family': 'Comedy, Farce & Chaos',
        'directive': 'PLAY STYLE — MISTAKEN IDENTITY: Dwell on assumptions, double meanings, disguise, missed introductions, status reversal, and the player choosing whether to correct. Compress violent resolution and exposition that clears things too fast. Let tension build as escalating confusion toward reveal. Make victory mean escape, benefit, confess, or restore order at the right moment; make loss come from wrong person is harmed, reveal comes too late, or the false role traps you.',
    },
    'prank_war': {
        'name': 'Prank War',
        'family': 'Comedy, Farce & Chaos',
        'directive': 'PLAY STYLE — PRANK WAR: Dwell on setup, misdirection, timing, reveals, escalation etiquette, alliances, and laughing aftermath. Compress cruelty without play and unrelated plot. Let tension build as escalating exchange — each prank raises ingenuity and risk. Make victory mean land the decisive prank without crossing the line; make loss come from go too far, lose consent, get outplayed, or turn fun into harm.',
    },
    'bureaucratic_absurdity': {
        'name': 'Bureaucratic Absurdity',
        'family': 'Comedy, Farce & Chaos',
        'directive': 'PLAY STYLE — BUREAUCRATIC ABSURDITY: Dwell on forms, contradictory rules, offices, stamps, waiting rooms, petty authority, loopholes, and comic helplessness. Compress heroic shortcuts that skip the institution. Let tension build as procedural maze — progress is always sideways. Make victory mean obtain the permit, approval, stamp, or loophole and keep sanity; make loss come from get trapped in the loop, lose documents, or become part of the bureaucracy.',
    },
    'odd_couple_mission': {
        'name': 'Odd-Couple Mission',
        'family': 'Comedy, Farce & Chaos',
        'directive': 'PLAY STYLE — ODD-COUPLE MISSION: Dwell on clashing habits, forced proximity, banter, mutual irritation, complementary skills, and reluctant respect. Compress solo competence and plot that separates the pair too long. Let tension build as episodic friction warming into partnership. Make victory mean complete the mission and achieve a new working bond; make loss come from split, sabotage each other, or refuse the lesson in the contrast.',
    },
    'competition_tournament': {
        'name': 'Competition / Tournament',
        'family': 'Competition, Status & Proving Grounds',
        'directive': 'PLAY STYLE — COMPETITION / TOURNAMENT: Dwell on matches, heats, rivals, standings, clutch moments, styles, crowd, and narrowing field. Compress downtime and off-field logistics. Let tension build as episodic spikes escalating to a final. Make victory mean win the championship or decisive final; make loss come from elimination, defeat by rival, choking under pressure, or rule breach.',
    },
    'sports_match': {
        'name': 'Sports Match',
        'family': 'Competition, Status & Proving Grounds',
        'directive': 'PLAY STYLE — SPORTS MATCH: Dwell on score, clock, formations, stamina, substitutions, crowd pressure, fouls, and tactical adjustments. Compress backstory during live play except as pressure. Let tension build as live oscillation — momentum shifts until final whistle. Make victory mean win the match or achieve the needed result; make loss come from lose, draw when win was needed, injury collapse, or penalty failure.',
    },
    'racing': {
        'name': 'Racing',
        'family': 'Competition, Status & Proving Grounds',
        'directive': 'PLAY STYLE — RACING: Dwell on lines, corners, drafting, weather, vehicle feel, rivals, split times, and the nerve to push. Compress slow strategy unrelated to speed. Let tension build as continuous pressure with overtake spikes. Make victory mean finish first or meet target time without wrecking; make loss come from crash, fall behind, misjudge risk, or lose control at the key moment.',
    },
    'reality_show_strategy': {
        'name': 'Reality Show Strategy',
        'family': 'Competition, Status & Proving Grounds',
        'directive': 'PLAY STYLE — REALITY SHOW STRATEGY: Dwell on alliances, confessionals, edits, challenge performance, social reads, betrayals, vote math, and jury perception. Compress private life outside the show. Let tension build as episode cycle — challenge, scramble, vote, fallout. Make victory mean reach the end and win votes, audience, or prize; make loss come from be eliminated, misread the room, look too threatening, or betray too visibly.',
    },
    'gambling_wager_drama': {
        'name': 'Gambling / Wager Drama',
        'family': 'Competition, Status & Proving Grounds',
        'directive': 'PLAY STYLE — GAMBLING / WAGER DRAMA: Dwell on stakes, chips, probability, tells, table talk, losses, addiction pressure, and all-in moments. Compress deterministic victory and unrelated action. Let tension build as swing pressure — fortune and nerve oscillate. Make victory mean win the pot, debt, information, or wager without losing self-control; make loss come from go bust, tilt, get read, cheat badly, or risk what should not be risked.',
    },
    'epic_quest_saga': {
        'name': 'Epic Quest / Saga',
        'family': 'Mythic, Spiritual & Symbolic',
        'directive': 'PLAY STYLE — EPIC QUEST / SAGA: Dwell on trials, set-pieces, allies, transformation, rising stakes, omens, and the final confrontation. Compress connective travel and repetitive low-stakes activity. Let tension build as escalating ratchet toward a destined climax. Make victory mean achieve the great goal as someone transformed by the road; make loss come from fall at a trial, arrive unworthy, or fail at the peak.',
    },
    'rite_of_passage': {
        'name': 'Rite of Passage',
        'family': 'Mythic, Spiritual & Symbolic',
        'directive': 'PLAY STYLE — RITE OF PASSAGE: Dwell on ritual rules, elders, taboos, ordeals, symbols, witnesses, and before/after identity. Compress generic adventure that does not change status. Let tension build as threshold tension — ordeal narrows into recognition. Make victory mean complete the rite and assume the new role truthfully; make loss come from fail the rite, cheat the meaning, or be recognized falsely.',
    },
    'prophecy_fate_game': {
        'name': 'Prophecy / Fate Game',
        'family': 'Mythic, Spiritual & Symbolic',
        'directive': 'PLAY STYLE — PROPHECY / FATE GAME: Dwell on omens, ambiguous wording, attempts to avoid fate, self-fulfilling moves, interpreters, and tragic irony. Compress random prediction with no agency. Let tension build as foreknowledge spiral — attempts to control fate tighten it. Make victory mean fulfill fate wisely, avert doom, or redefine the prophecy’s meaning; make loss come from cause the prophecy by resisting it, misread it, or surrender agency.',
    },
    'divine_trial': {
        'name': 'Divine Trial',
        'family': 'Mythic, Spiritual & Symbolic',
        'directive': 'PLAY STYLE — DIVINE TRIAL: Dwell on signs, offerings, vows, divine silence, impossible choices, sacred law, and judgment scenes. Compress secular logistics and combat that dodges the test. Let tension build as ritual pressure with revelation at judgment. Make victory mean pass, bargain, refuse rightly, or transform under divine scrutiny; make loss come from fail through pride, literalism, cowardice, or false devotion.',
    },
    'underworld_descent': {
        'name': 'Underworld Descent',
        'family': 'Mythic, Spiritual & Symbolic',
        'directive': 'PLAY STYLE — UNDERWORLD DESCENT: Dwell on thresholds, guides, shades, symbolic landscapes, rules of the dead, temptations to stay, and the return. Compress ordinary geography and mundane combat. Let tension build as descent-and-return — deepening strangeness to a retrieval pivot. Make victory mean return with the person, truth, relic, or self changed; make loss come from look back, stay, lose what you came for, or return hollow.',
    },
    'fairy_tale_bargain': {
        'name': 'Fairy-Tale Bargain',
        'family': 'Mythic, Spiritual & Symbolic',
        'directive': 'PLAY STYLE — FAIRY-TALE BARGAIN: Dwell on oaths, names, gifts, thresholds, hospitality, hidden costs, literal promises, and cunning reversals. Compress brute force and modern legal realism. Let tension build as rule tension — every word binds more tightly. Make victory mean win the bargain, escape the clause, or use the rule justly; make loss come from break taboo, owe the wrong debt, lose name or freedom, or misword the promise.',
    },
    'time_travel_paradox': {
        'name': 'Time Travel Paradox',
        'family': 'Time, Reality & Metafiction',
        'directive': 'PLAY STYLE — TIME TRAVEL PARADOX: Dwell on causal chains, historical pressure points, doubles, erased memories, paradox costs, and moral ownership of timelines. Compress ordinary travel and action without causal consequence. Let tension build as branching ratchet — each intervention changes the board. Make victory mean achieve the needed timeline while accepting or containing costs; make loss come from erase what mattered, cause worse history, duplicate yourself fatally, or trap the loop.',
    },
    'alternate_history_intervention': {
        'name': 'Alternate History Intervention',
        'family': 'Time, Reality & Metafiction',
        'directive': 'PLAY STYLE — ALTERNATE HISTORY INTERVENTION: Dwell on historical constraints, key actors, institutions, technology limits, butterfly effects, and rival interventions. Compress anachronistic ease and isolated heroics detached from systems. Let tension build as counterfactual accretion — small changes reveal structural resistance. Make victory mean secure the desired divergence or preserve the timeline knowingly; make loss come from create worse outcomes, fail to understand context, or become the tyrant of history.',
    },
    'multiverse_branching': {
        'name': 'Multiverse Branching',
        'family': 'Time, Reality & Metafiction',
        'directive': 'PLAY STYLE — MULTIVERSE BRANCHING: Dwell on contrasting versions, emotional comparison, identity dissonance, branch rules, and choices between worlds. Compress simple travelogue between gimmick worlds. Let tension build as comparative revelation — each branch reframes the others. Make victory mean choose, reconcile, repair, or survive among branches without erasing what matters; make loss come from collapse branches, lose selfhood, choose fantasy over responsibility, or harm alternate lives.',
    },
    'simulation_escape': {
        'name': 'Simulation Escape',
        'family': 'Time, Reality & Metafiction',
        'directive': 'PLAY STYLE — SIMULATION ESCAPE: Dwell on glitches, déjà vu, system rules, NPC personhood, admin traces, exploits, and the dread of outside truth. Compress ordinary worldbuilding after artificiality is known. Let tension build as awakening ratchet — suspicion becomes rule mastery. Make victory mean escape, rewrite, liberate others, or choose the simulation knowingly; make loss come from be reset, trapped, used by the system, or destroy people who are real enough.',
    },
    'reality_editing': {
        'name': 'Reality Editing',
        'family': 'Time, Reality & Metafiction',
        'directive': 'PLAY STYLE — REALITY EDITING: Dwell on the exact edit, unintended side effects, memory conflicts, ethical use, resistance from reality, and rollback costs. Compress combat or plot that ignores rewritten facts. Let tension build as cascade spiral — small edits compound into instability. Make victory mean create the needed change without losing coherence or conscience; make loss come from break causality, erase people, destabilize reality, or become addicted to revision.',
    },
    'language_decipherment': {
        'name': 'Language Decipherment',
        'family': 'Communication, Collection & Interpretation',
        'directive': 'PLAY STYLE — LANGUAGE DECIPHERMENT: Dwell on repeated signs, gestures, mistakes, grammar guesses, inscriptions, idioms, names, and breakthroughs in mutual comprehension. Compress instant translation and action unrelated to communication. Let tension build as semantic accretion — fragments become fluency. Make victory mean communicate accurately enough to act, bond, or avoid harm; make loss come from mistranslate, offend, issue the wrong command, or never move beyond symbols.',
    },
    'signal_from_the_unknown': {
        'name': 'Signal from the Unknown',
        'family': 'Communication, Collection & Interpretation',
        'directive': 'PLAY STYLE — SIGNAL FROM THE UNKNOWN: Dwell on static, repetition, filters, false positives, timing, source tracing, possible intent, and response protocol. Compress random prophecy and combat before interpretation. Let tension build as signal clarity ratchet. Make victory mean identify source and meaning, then respond safely; make loss come from misread noise as message, answer hostilely, reveal yourself, or ignore a warning.',
    },
    'interview_game': {
        'name': 'Interview Game',
        'family': 'Communication, Collection & Interpretation',
        'directive': 'PLAY STYLE — INTERVIEW GAME: Dwell on question order, tone, evasions, tells, rapport, pressure, silence, and the moment a guarded answer opens. Compress evidence gathering outside the conversation. Let tension build as verbal pressure curve — rapport and pressure trade off. Make victory mean obtain the needed truth or understanding without poisoning the source; make loss come from shut them down, accept a lie, coerce falsely, or miss the human meaning.',
    },
    'collectathon_field_guide': {
        'name': 'Collectathon / Field Guide',
        'family': 'Communication, Collection & Interpretation',
        'directive': 'PLAY STYLE — COLLECTATHON / FIELD GUIDE: Dwell on checklists, categories, rarity, clues to missing entries, collection displays, and satisfaction of completion. Compress deep drama unless tied to the set. Let tension build as completion accretion — gaps become increasingly meaningful. Make victory mean complete the set or understand the system through the catalogue; make loss come from miss rare entries, misclassify, damage specimens, or complete without meaning.',
    },
    'museum_archive_curation': {
        'name': 'Museum / Archive Curation',
        'family': 'Communication, Collection & Interpretation',
        'directive': 'PLAY STYLE — MUSEUM / ARCHIVE CURATION: Dwell on provenance, preservation, display choices, contested ownership, labels, public interpretation, and the collection’s story. Compress generic treasure accumulation and action unrelated to curation. Let tension build as ordered accretion with exhibition payoff. Make victory mean create a truthful, compelling, preserved collection; make loss come from misattribute, exploit, damage, hoard, or present a false story.',
    },
    'epistolary_correspondence': {
        'name': 'Epistolary / Correspondence',
        'family': 'Communication, Collection & Interpretation',
        'directive': 'PLAY STYLE — EPISTOLARY / CORRESPONDENCE: Dwell on voice, omissions, delay, handwriting or medium, unsent drafts, misread tone, and intimacy through distance. Compress immediate face-to-face resolution and action outside the correspondence. Let tension build as delayed accretion — meaning grows between messages. Make victory mean reach understanding, love, warning, confession, or coordinated action through the exchange; make loss come from message lost, tone misread, truth delayed too long, or correspondence weaponized.',
    },
    'power_ascent': {
        'name': 'Power Ascent',
        'family': 'Transgression, Power & Ensemble Forms',
        'directive': 'PLAY STYLE — POWER ASCENT: Dwell on training, upgrades, status jumps, former threats becoming manageable, temptation, and changes in how others react. Compress static power level and challenges unrelated to growth. Let tension build as escalating empowerment with moral stress. Make victory mean become formidable and use power to achieve the chosen aim; make loss come from become hollow, abusive, dependent on power, or meet a cost you ignored.',
    },
    'villain_campaign': {
        'name': 'Villain Campaign',
        'family': 'Transgression, Power & Ensemble Forms',
        'directive': 'PLAY STYLE — VILLAIN CAMPAIGN: Dwell on minions, schemes, intimidation, temptation of others, rival villains, public fear, and consequences of cruelty. Compress heroic morality frames that soften agency. Let tension build as domination ratchet with rebellion spikes. Make victory mean achieve the villainous objective and keep control over the consequences; make loss come from be overthrown, redeemed against intent, betrayed, or consumed by the evil used.',
    },
    'crime_lord_rise': {
        'name': 'Crime Lord Rise',
        'family': 'Transgression, Power & Ensemble Forms',
        'directive': 'PLAY STYLE — CRIME LORD RISE: Dwell on territory, crews, protection, supply, rivals, cops, bribes, family pressure, and legitimacy laundering. Compress single-score focus after the enterprise scale begins. Let tension build as enterprise accretion with heat spikes. Make victory mean control profitable territory and survive rivals and law; make loss come from crew betrayal, war, arrest, public heat, or loss of legitimacy.',
    },
    'monster_perspective': {
        'name': 'Monster Perspective',
        'family': 'Transgression, Power & Ensemble Forms',
        'directive': 'PLAY STYLE — MONSTER PERSPECTIVE: Dwell on hunger, instincts, alien senses, concealment, prey, taboos, remnants of humanity, and moral or biological limits. Compress ordinary human social drama not reframed by monstrosity. Let tension build as appetite cycle — need rises until fed, sublimated, or resisted. Make victory mean satisfy need, preserve self, or define a new monstrous code; make loss come from exposure, starvation, loss of self, uncontrolled harm, or being hunted down.',
    },
    'legacy_campaign': {
        'name': 'Legacy Campaign',
        'family': 'Transgression, Power & Ensemble Forms',
        'directive': 'PLAY STYLE — LEGACY CAMPAIGN: Dwell on persistent consequences, altered locations, inherited tools, scars, memorials, faction memory, and generational callbacks. Compress reset-button episodes and consequences that vanish. Let tension build as long-horizon accretion — history becomes playable terrain. Make victory mean leave a meaningful legacy or transform the world across arcs; make loss come from waste the inheritance, repeat disasters, or leave the world poorer and less free.',
    },
    'collaborative_quest_party': {
        'name': 'Collaborative Quest Party',
        'family': 'Transgression, Power & Ensemble Forms',
        'directive': 'PLAY STYLE — COLLABORATIVE QUEST PARTY: Dwell on role specialties, table talk, party bonds, interlocking abilities, shared decisions, and spotlight handoffs. Compress solo-protagonist dominance and scenes where others are decorative. Let tension build as ensemble rhythm — challenges rotate focus and combine strengths. Make victory mean complete the quest as a party with bonds and contributions intact; make loss come from party fracture, spotlight imbalance, unserved roles, or failure to coordinate.',
    },
    'live_action_social_intrigue': {
        'name': 'Live-Action Social Intrigue',
        'family': 'Transgression, Power & Ensemble Forms',
        'directive': 'PLAY STYLE — LIVE-ACTION SOCIAL INTRIGUE: Dwell on physical presence, side conversations, costumes, whispered deals, public announcements, timed reveals, and embodied etiquette. Compress private monologue and action outside the event space. Let tension build as event pressure — clocks and reveals reshape the room. Make victory mean achieve faction, personal, or relational goals before the event ends; make loss come from be exposed, isolated, outvoted, socially trapped, or miss the timed opportunity.',
    },
    'asymmetric_information_game': {
        'name': 'Asymmetric Information Game',
        'family': 'Transgression, Power & Ensemble Forms',
        'directive': 'PLAY STYLE — ASYMMETRIC INFORMATION GAME: Dwell on private briefings, selective disclosure, mistrust, message limits, role incentives, and moments when hidden knowledge matters. Compress omniscient narration and fully shared plans. Let tension build as information tension — revelations alter coordination and suspicion. Make victory mean use distributed knowledge to achieve the group or personal objective; make loss come from withhold too much, reveal too much, miscoordinate, or let hidden incentives fracture play.',
    },
}
