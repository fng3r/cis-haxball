# Replay relevance audit — ЧР, 17 сезон

Snapshot: 2026-11-07T17:18:13.441279+00:00. Heuristic: `experimental-v1`. **Read-only; no saved decisions changed.**

119 played matches, 161 supported recording links, 246 analyzed games. 8 matches need review; 111 have no outstanding flags (including already-excluded restarts and expected technical-result gaps).

Proposals: 231 retain, 14 exclusion candidates, 1 retain pending review.

**2 newly proposed exclusions**; the remaining exclusion candidates already match saved decisions. Review these first:

- Match [6864](http://localhost:8000/championship/match/6864), R1/G2, part ID 50: 2.70s, red/blue score 1:0. Evidence: fewer_than_required_players, differs_from_saved_inclusion.
- Match [6922](http://localhost:8000/championship/match/6922), R1/G2, part ID 108: 143.57s, red/blue score 1:4. Evidence: short_extra_beside_two_full_halves, differs_from_saved_inclusion.

Observed major protocol mismatches: 0. That branch, split-half cases and golden-goal overtime are covered by synthetic tests but need real examples before claiming validation.

## How to read this experiment

- Exclusion is a recommendation, never an applied edit. Raw results and historical data are untouched.
- R/B counts are distinct active players over the entire game, including substitutions. Known aliases are deduplicated; spectators are ignored. This run assumes 4v4.
- Fewer than four on either side is strong evidence. A major protocol mismatch requires a complete protocol (≥4 per team), ≥4 confidently identified outsiders and outsiders exceeding half the roster or occupying ≥75% of one side. Unknown/ambiguous nicknames are not outsiders.
- Games ≥7:30 are potential full parts (recognition tolerance). The first two are regulation candidates. Extra games <4:00 beside two full halves are restart candidates, including scored warmups. Short games after regulation in playoffs remain under review for golden goals.
- When two full halves are absent, adjacent groups of 2–4 shorter games totaling 8:00±15s are possible continuations, retained for review. Missing halves never justify including an obviously unrelated game.
- Only goal events through 8:00 per retained game enter the diagnostic score. Later goals do not. Fair-play goals can still differ from the report. Score mismatch requests review, never exclusion.
- Source-list order is provisional across recordings. No native clock-offset/end-reason metadata is available in the stored export; continuation and golden-goal classification remain tentative. The score for split halves is also tentative because the eight-minute boundary spans segments.
- Saved inclusion is shown separately: it may be a deliberate correction. No training labels or manual ground truth exist yet, so this is a consistency audit, not a measured accuracy claim.
- Technical results are exempt from score/coverage checks. Confirmed exclusions already matching saved decisions are listed in the exclusion appendix, not counted as outstanding review cases.

## Review index

| Match | Competition / tour | Official | Through 8:00¹ | Review reasons |
|---|---|---|---|---|
| [6864](http://localhost:8000/championship/match/6864) demonicca — FC United | Единая лига / 1 тур (Единая лига – Регулярка) | 1:3 | 1:3 | differs_from_saved_inclusion, fewer_than_required_players |
| [6883](http://localhost:8000/championship/match/6883) One more pass — Коляска Хокинга | Единая лига / 3 тур (Единая лига – Регулярка) | 11:4 | 12:5 | score_difference_review_only |
| [6890](http://localhost:8000/championship/match/6890) Rockets — demonicca | Единая лига / 4 тур (Единая лига – Регулярка) | 9:7 | 10:8 | score_difference_review_only |
| [6913](http://localhost:8000/championship/match/6913) BEGEJMOTLARP — Коляска Хокинга | Единая лига / 7 тур (Единая лига – Регулярка) | 6:3 | 7:4 | score_difference_review_only |
| [6922](http://localhost:8000/championship/match/6922) AS Tatarstan — BEGEJMOTLARP | Единая лига / 8 тур (Единая лига – Регулярка) | 11:7 | 11:7 | differs_from_saved_inclusion, short_extra_beside_two_full_halves |
| [6944](http://localhost:8000/championship/match/6944) BEGEJMOTIK — AS Tatarstan | Единая лига / 11 тур (Единая лига – Регулярка) | 5:5 | 6:6 | score_difference_review_only |
| [6997](http://localhost:8000/championship/match/6997) demonicca — FC United | Кубок России / 1 тур (Кубок России) | 5:11 | 5:10 | recorded_time_short_of_match_duration, regulation_coverage_uncertain, score_difference_review_only, short_game_without_clear_role |
| [7002](http://localhost:8000/championship/match/7002) KUMYS POWER — ACES | Кубок России / 2 тур (Кубок России) | 5:2 | 6:3 | score_difference_review_only |

¹ Diagnostic only; source order, side mapping, continuations, fair-play and overtime need review.

## Game-by-game evidence for flagged matches

### Match 6864: demonicca — FC United

[Open match](http://localhost:8000/championship/match/6864). Official 1:3, duration 16:00. Issues: game-level only.

Review the newly proposed exclusion below against the surrounding regulation candidates.

| Recording / game² / part ID | Saved label; included | Active | R:B | Players R/B | Matched; outsiders; unknown | Proposal / role | Evidence |
|---|---|---|---|---|---|---|---|
| [R1 / G1](https://replay.thehax.pl/83aac0a0-8288-4971-973c-bab0916ffd35) / 47 | 1 тайм; True | 7:59 | 0:3 | 4/4 | 8; 0; 0 | retain / regulation_candidate | — |
| [R1 / G2](https://replay.thehax.pl/83aac0a0-8288-4971-973c-bab0916ffd35) / 50 | 2 тайм; True | 0:03 | 1:0 | 4/3 | 7; 0; 0 | exclude / irrelevant_candidate | fewer_than_required_players, differs_from_saved_inclusion |
| [R1 / G3](https://replay.thehax.pl/83aac0a0-8288-4971-973c-bab0916ffd35) / 53 | Доп. время 1; True | 8:00 | 1:0 | 4/4 | 8; 0; 0 | retain / regulation_candidate | — |


### Match 6883: One more pass — Коляска Хокинга

[Open match](http://localhost:8000/championship/match/6883). Official 11:4, duration 16:00. Issues: score_difference_review_only.

Both teams have 1 extra replay goal(s). This is consistent with a fair-play exchange, but requires confirmation. Keep the games; do not force the replay score to match.

| Recording / game² / part ID | Saved label; included | Active | R:B | Players R/B | Matched; outsiders; unknown | Proposal / role | Evidence |
|---|---|---|---|---|---|---|---|
| [R1 / G1](https://replay.thehax.pl/af778107-765e-4ee3-b618-ce1c7b49b903) / 14 | 1 тайм; True | 8:00 | 7:3 | 4/4 | 8; 0; 0 | retain / regulation_candidate | — |
| [R1 / G2](https://replay.thehax.pl/af778107-765e-4ee3-b618-ce1c7b49b903) / 16 | 2 тайм; True | 8:00 | 5:2 | 5/4 | 9; 0; 0 | retain / regulation_candidate | — |


### Match 6890: Rockets — demonicca

[Open match](http://localhost:8000/championship/match/6890). Official 9:7, duration 16:00. Issues: score_difference_review_only.

Both teams have 1 extra replay goal(s). This is consistent with a fair-play exchange, but requires confirmation. Keep the games; do not force the replay score to match.

| Recording / game² / part ID | Saved label; included | Active | R:B | Players R/B | Matched; outsiders; unknown | Proposal / role | Evidence |
|---|---|---|---|---|---|---|---|
| [R1 / G1](https://replay.thehax.pl/b6976710-86da-490c-a790-cbae3913a65a) / 85 | 1 тайм; True | 8:00 | 5:3 | 4/4 | 8; 0; 0 | retain / regulation_candidate | — |
| [R1 / G2](https://replay.thehax.pl/b6976710-86da-490c-a790-cbae3913a65a) / 86 | 2 тайм; True | 8:03 | 6:5 | 4/5 | 9; 0; 0 | retain / regulation_candidate | — |


### Match 6913: BEGEJMOTLARP — Коляска Хокинга

[Open match](http://localhost:8000/championship/match/6913). Official 6:3, duration 16:00. Issues: score_difference_review_only.

Both teams have 1 extra replay goal(s). This is consistent with a fair-play exchange, but requires confirmation. Keep the games; do not force the replay score to match.

| Recording / game² / part ID | Saved label; included | Active | R:B | Players R/B | Matched; outsiders; unknown | Proposal / role | Evidence |
|---|---|---|---|---|---|---|---|
| [R1 / G1](https://replay.thehax.pl/84eb3db2-0841-4632-9328-8f5c615d4009) / 112 | 1 тайм; True | 8:00 | 2:1 | 4/4 | 8; 0; 0 | retain / regulation_candidate | — |
| [R2 / G1](https://replay.thehax.pl/63dfc60e-725a-4c05-a0f7-58fb69c8aa0c) / 121 | 2 тайм; True | 8:00 | 5:3 | 4/4 | 8; 0; 0 | retain / regulation_candidate | — |


### Match 6922: AS Tatarstan — BEGEJMOTLARP

[Open match](http://localhost:8000/championship/match/6922). Official 11:7, duration 16:00. Issues: game-level only.

Review the newly proposed exclusion below against the surrounding regulation candidates.

| Recording / game² / part ID | Saved label; included | Active | R:B | Players R/B | Matched; outsiders; unknown | Proposal / role | Evidence |
|---|---|---|---|---|---|---|---|
| [R1 / G1](https://replay.thehax.pl/3da62df4-81c3-44b8-a1ed-34aa3c99c7d0) / 107 | 1 тайм; True | 8:00 | 5:4 | 4/4 | 8; 0; 0 | retain / regulation_candidate | — |
| [R1 / G2](https://replay.thehax.pl/3da62df4-81c3-44b8-a1ed-34aa3c99c7d0) / 108 | 2 тайм; True | 2:24 | 1:4 | 4/4 | 8; 0; 0 | exclude / restart_candidate | short_extra_beside_two_full_halves, differs_from_saved_inclusion |
| [R1 / G3](https://replay.thehax.pl/3da62df4-81c3-44b8-a1ed-34aa3c99c7d0) / 109 | Доп. время 1; True | 8:00 | 6:3 | 4/5 | 9; 0; 0 | retain / regulation_candidate | — |


### Match 6944: BEGEJMOTIK — AS Tatarstan

[Open match](http://localhost:8000/championship/match/6944). Official 5:5, duration 16:00. Issues: score_difference_review_only.

Both teams have 1 extra replay goal(s). This is consistent with a fair-play exchange, but requires confirmation. Keep the games; do not force the replay score to match.

| Recording / game² / part ID | Saved label; included | Active | R:B | Players R/B | Matched; outsiders; unknown | Proposal / role | Evidence |
|---|---|---|---|---|---|---|---|
| [R1 / G1](https://replay.thehax.pl/9b7eafe5-8f94-47de-b3db-16ec13caf828) / 168 | 1 тайм; True | 8:00 | 2:4 | 4/4 | 8; 0; 0 | retain / regulation_candidate | — |
| [R2 / G1](https://replay.thehax.pl/ae5ed140-3c6d-46f7-ad28-13f87daae164) / 196 | 2 тайм; True | 8:00 | 4:2 | 4/4 | 8; 0; 0 | retain / regulation_candidate | — |


### Match 6997: demonicca — FC United

[Open match](http://localhost:8000/championship/match/6997). Official 5:11, duration 16:00. Issues: regulation_coverage_uncertain, recorded_time_short_of_match_duration, score_difference_review_only.

The retained recorded play is shorter than the match duration. Check for a missing recording or a recording started mid-half; retain the short game until its role is established.

| Recording / game² / part ID | Saved label; included | Active | R:B | Players R/B | Matched; outsiders; unknown | Proposal / role | Evidence |
|---|---|---|---|---|---|---|---|
| [R1 / G1](https://replay.thehax.pl/504919d9-d10f-4297-91d1-c46171aead92) / 212 | 1 тайм; True | 6:10 | 3:4 | 4/4 | 8; 0; 0 | review / unclassified | short_game_without_clear_role |
| [R1 / G2](https://replay.thehax.pl/504919d9-d10f-4297-91d1-c46171aead92) / 213 | 2 тайм; True | 8:00 | 2:6 | 4/4 | 8; 0; 0 | retain / regulation_candidate | — |


### Match 7002: KUMYS POWER — ACES

[Open match](http://localhost:8000/championship/match/7002). Official 5:2, duration 16:00. Issues: score_difference_review_only.

Both teams have 1 extra replay goal(s). This is consistent with a fair-play exchange, but requires confirmation. Keep the games; do not force the replay score to match.

| Recording / game² / part ID | Saved label; included | Active | R:B | Players R/B | Matched; outsiders; unknown | Proposal / role | Evidence |
|---|---|---|---|---|---|---|---|
| [R1 / G1](https://replay.thehax.pl/3d8455cb-ec3c-4924-a948-29e54ddadb4f?t=7) / 229 | 1 тайм; True | 8:00 | 3:1 | 4/4 | 8; 0; 0 | retain / regulation_candidate | — |
| [R2 / G1](https://replay.thehax.pl/f72f2d5b-431b-4d8a-9e05-a833cc8bf7da?t=15) / 232 | 2 тайм; True | 8:00 | 3:2 | 5/4 | 9; 0; 0 | retain / regulation_candidate | — |


## All exclusion candidates

| Match | Recording / game / part ID | Active | R:B | Currently included | Evidence |
|---|---|---|---|---|---|
| [6863](http://localhost:8000/championship/match/6863) | R1/G2 / 49 | 0:04 | 0:0 | False | short_extra_beside_two_full_halves |
| [6864](http://localhost:8000/championship/match/6864) | R1/G2 / 50 | 0:03 | 1:0 | True | fewer_than_required_players, differs_from_saved_inclusion |
| [6865](http://localhost:8000/championship/match/6865) | R1/G2 / 19 | 0:02 | 0:0 | False | short_extra_beside_two_full_halves |
| [6866](http://localhost:8000/championship/match/6866) | R1/G2 / 10 | 0:06 | 0:0 | False | short_extra_beside_two_full_halves |
| [6873](http://localhost:8000/championship/match/6873) | R1/G2 / 23 | 0:04 | 0:0 | False | short_extra_beside_two_full_halves |
| [6874](http://localhost:8000/championship/match/6874) | R1/G2 / 12 | 0:02 | 0:0 | False | short_extra_beside_two_full_halves |
| [6920](http://localhost:8000/championship/match/6920) | R1/G1 / 136 | 0:08 | 0:0 | False | short_extra_beside_two_full_halves |
| [6922](http://localhost:8000/championship/match/6922) | R1/G2 / 108 | 2:24 | 1:4 | True | short_extra_beside_two_full_halves, differs_from_saved_inclusion |
| [6949](http://localhost:8000/championship/match/6949) | R1/G2 / 178 | 0:02 | 0:0 | False | short_extra_beside_two_full_halves |
| [6949](http://localhost:8000/championship/match/6949) | R1/G3 / 179 | 0:01 | 0:0 | False | short_extra_beside_two_full_halves |
| [6955](http://localhost:8000/championship/match/6955) | R1/G1 / 201 | 0:05 | 0:0 | False | short_extra_beside_two_full_halves |
| [6960](http://localhost:8000/championship/match/6960) | R1/G3 / 219 | 0:09 | 0:0 | False | fewer_than_required_players |
| [6999](http://localhost:8000/championship/match/6999) | R1/G1 / 214 | 0:03 | 0:0 | False | short_extra_beside_two_full_halves |
| [7004](http://localhost:8000/championship/match/7004) | R1/G2 / 227 | 0:05 | 0:0 | False | short_extra_beside_two_full_halves |

² G is one-based for review; JSON `game_id` is the engine’s zero-based identifier.
