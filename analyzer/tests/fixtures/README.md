# Replay fixtures

Real match recordings supplied by the project owner on 2026-11-06. Files are
renamed for tests; their bytes are unchanged. The upstream sample recordings
have been removed.

| Fixture | Original filename | Native stadium | Matches / final scores |
|---|---|---|---|
| `futsal.hbr2` | `cis5_30-10-26T21-18-50.hbr2` | Futsal 3x3 4x4 | 1–7 |
| `futsal-multi.hbr2` | `HBReplay-2026-11-04-22h20m-6aeb85d328e750.73685187.hbr2` | Futsal 3x3 4x4 | 3–2, 7–0 |
| `cis5.hbr2` | `cis5_28-10-26T22-25-25-6ae2535f857db9.40079376.hbr2` | BFF Big v4 | 3–3 |
| `cis4.hbr2` | `cis4_28-10-26T22-39-26.hbr2` | BFF Big v4 | 2–12 |

The November recording exercises multiple games and substitutions. `cis4` also
contains a substitution. `cis5` ends without a native game-end event. Both October 28
files identify their stadium as BFF Big v4 in the decoded data; neutral fixture
names avoid assigning a different ruleset from the filename alone.

## Integrity

SHA-256 checksums of the supplied files:

- `futsal.hbr2`: `9cbd45b624de3275120896c1c37875bb84a8fc6289561765a152f618a7d00b2b`
- `futsal-multi.hbr2`: `ac236a9055b656e94e33c557955b161aceb5201ce116861604b48b84f61394f1`
- `cis5.hbr2`: `9843e7dcaef30443662be5152e2afe17c122ec774a651a97bd26dc57480eabda`
- `cis4.hbr2`: `c5e3af0c481c28257e749c92c5c1f9ae0c6bfd7ea9f85c0aaf29db25620041b4`

## What the tests establish

`../replay-fixtures.js` records native scores and recording ticks for goals, plus
regression baselines for the unchanged original engine. Physics-equivalence tests
step every recording through both runtimes and compare scores, clocks, player and
ball positions/velocities once per second and at the final tick.

V2 tests exercise all four recordings, checking game boundaries, substitutions,
played time, spatial maps, event links, player/team/recording aggregates, optional
tracking and exports. Synthetic scenarios remain to verify explicit classification
rules and cases not represented by these recordings (such as duplicate names).

These files do not contain manually annotated pass, shot, recovery or assist
labels. Regression values and conservation checks do not establish human-verified
accuracy of inferred actions. The tests do not treat original-engine scorer or
assist attribution as ground truth for v2's different contact-aware rules.
