# Replay metrics research

Research date: 2026-11-06. This document is a catalogue of possibilities, not an approved implementation plan. We will revisit it to choose next steps.

The decoded replay is enough to build substantially richer analysis than the original analyzer provides. We can reconstruct the ball, players, inputs, and physics throughout the recording. Most useful base metrics need no machine learning; advanced metrics such as expected goals need a dataset of replays to train and validate against.

The important distinction is between **observed events**, **calculated measurements**, and **interpretations**. A successful kick is observable. Distance travelled is calculable. Whether a kick was intended as a pass or shot is an interpretation.

The engine was inspected and a fixture decoded directly to confirm the available state.

## Available replay data

| Data | What is available |
|---|---|
| Time | Recording ticks, reconstructed game state, game clock, score and phases such as active play, pauses and goal resets. |
| Players | Replay-local ID, nickname, team, presence on the field and changes over time. |
| Player movement | Position, velocity, radius and physical properties. |
| Player inputs | Movement/kick input state applied by the simulation, including kick-related state and cooldowns. |
| Ball movement | Position, velocity, radius and physical properties. |
| Stadium | Goal segments, boundaries, walls, obstacles, collision groups, damping, acceleration, kick strength and other physics settings. |
| Events | Recorded actions and reconstructed events, including joins, team changes, game starts/stops, successful kicks and goals. |

This is available through the [runtime adapter](src/engine/runtime-adapter.inc). The engine advances the simulation at **60 ticks per second**. The optional exported frames are sampled every four ticks, but new metrics can run on every simulation tick.

**The current JSON export contains only part of this information.** Heatmap cells cannot reconstruct movement order, and current spatial event exports omit much of the timing and velocity information needed below.

## Definitions to establish first

These decisions affect almost every metric:

- **Contact versus kick:** touching the ball physically and successfully kicking it are different events. We should record both.
- **Possession versus last touch:** a player can kick the ball away and no longer control it. Possession should allow *controlled*, *contested* and *loose-ball* states.
- **Active time:** separate recording duration, match-clock duration, on-field time and active-play time. Exclude pauses and reset teleports from movement measurements.
- **Attack direction:** derive it from the goals defended by each team. Normalize coordinates so “forward” has the same meaning for both teams.
- **Identity:** use replay-local IDs and team-membership intervals, not nicknames. Connecting players across recordings requires app account mapping.
- **Rules and stadium:** thresholds should reflect player radius, pitch dimensions and physics. A threshold meaningful on Futsal may be wrong on another map.

In the lists below:

- **Direct** means observable or mechanically calculable from reconstructed state.
- **Defined** means feasible, but requires a documented classification rule.
- **Modelled** means an estimate requiring a predictive or behavioural model.

## Match, participation and scoring metrics

| Metric | Description | How to obtain it |
|---|---|---|
| **Score and goal timeline — Direct** | Goals, scoring team, score progression and goal times. | Read goal callbacks and score changes; attach recording tick and match-clock time. |
| **Game duration — Direct** | Match-clock duration and recording time occupied by each game. | Track starts, stops and clock changes separately from recording ticks. Mark games cut short by recording boundaries. |
| **Active-play duration — Direct** | Time when the ball and players are actually in live play. | Accumulate ticks in active phase, excluding pauses and goal/reset phases. |
| **On-field and active minutes — Direct** | Player participation, including substitutions and team switches. | Track intervals where each player belongs to a playing team; separately accumulate active ticks. |
| **Goals and own goals — Defined** | Attribute scoring contributions and accidental concessions. | Combine the scoring event with the preceding contact/kick chain. Define treatment of deflections, rather than relying solely on the last kicker. |
| **Assists — Defined** | Final teammate contribution before a goal. | Trace the scoring possession backward to the previous qualifying teammate action. Define timeout, opponent deflection and self-recovery rules. |
| **Secondary assists — Defined** | Contribution before the final assist. | Trace another qualifying teammate action backward in the same possession. |
| **Goal involvement — Defined** | Goals plus assists, optionally secondary assists. | Aggregate the attribution above without double-counting the scorer within one category. |
| **On-field goal difference — Direct** | Goals for minus goals against while a player was on the field. | At each goal, credit all participating players’ current team intervals. Useful context, but not isolated individual impact. |
| **Time leading, drawing and trailing — Direct** | Match-state exposure. | Integrate active time between score changes for each score state. |
| **Lineup and partnership results — Direct** | Performance while a particular lineup or player pair is present. | Segment by roster changes; aggregate minutes, goals and other metrics per lineup/pair. |
| **Per-minute and opportunity-adjusted rates — Direct/Defined** | Comparable rates despite different playing time or possession exposure. | Divide counts by active minutes, team possession time, opponent possessions or relevant opportunities. Show the denominator. |

## Ball involvement, possession and passing

| Metric | Description | How to obtain it |
|---|---|---|
| **Successful kicks — Direct** | Actual kicks that apply an impulse to the ball. | Instrument the existing successful-kick physics path; record actor, tick, ball position and before/after velocity. |
| **Physical touches — Direct with instrumentation** | Ball contacts without requiring a kick. | Instrument ball–player collision handling. Group sustained contact into one episode rather than counting every tick. |
| **Individual possession time — Defined** | Time a player plausibly controls the ball. | Combine contact history, ball proximity, relative velocity and ability to reach/kick it. Use hysteresis to avoid ownership flickering. |
| **Team possession — Defined** | Controlled time attributed to either team. | Aggregate individual control, retaining separate loose-ball and contested time. |
| **Possession sequences — Defined** | Number, duration and length of team possessions. | Start/end sequences on established control changes, goals and restarts. Small deflections need not automatically end possession. |
| **Completed transfers/passes — Defined** | Ball transferred between teammates. | Follow release by player A through to teammate B’s reception/control. Record physical reception separately from B’s next kick. |
| **Pass attempts and completion rate — Defined** | Passing success against attempted passes. | Classify releases as pass attempts, then resolve outcomes. Intended receiver and pass-versus-shot intent are not directly recorded, so ambiguous releases need an “unclassified” category. |
| **Passes received — Defined** | Successful receptions by a player. | Credit the receiving endpoint of a completed transfer. |
| **Pass distance and direction — Defined** | Short/long, forward/backward and lateral passing profile. | Measure release-to-reception displacement in normalized coordinates; optionally measure actual ball-path distance too. |
| **Progressive passes — Defined** | Passes that substantially advance toward the opponent’s goal. | Compare goal distance or longitudinal position before and after a completed pass. Use pitch-relative thresholds. |
| **Third/zone entries — Defined** | Movement of the ball into attacking areas. | Detect controlled passes or carries crossing configured zone boundaries. Count entries separately from time spent there. |
| **Possession losses — Defined** | Loss of established control to the opposition. | Attribute confirmed control transitions to the previous controller/releaser. Separate failed passes, tackles and uncontrolled releases. |
| **Retention under pressure — Defined** | Ability to keep the ball when closely challenged. | Flag pressure at reception or during control; measure whether possession survives a defined interval or subsequent action. |
| **Pass network — Defined** | Which players exchange the ball and how frequently. | Build a directed graph of completed transfers, weighted by count, progression or value. |
| **Passing combinations — Defined** | One-twos and repeated combinations. | Detect sequences such as A→B→A within bounded time and space, with no intervening opponent control. |

The distinction between a completed **transfer** and an intended **pass** is particularly useful here: the first is much easier to measure consistently.

## Shooting, chance creation and goalkeeping

| Metric | Description | How to obtain it |
|---|---|---|
| **Shot attempts — Defined** | Releases classified as attempts to score. | Use release position, ball velocity, goal geometry and trajectory. Include blocked and off-target attempts; retain uncertainty for ambiguous kicks. |
| **Shots on target — Defined** | Attempts heading into the goal opening before defensive intervention. | Project or simulate the ball’s path using its radius, damping and relevant walls. Define whether bank shots qualify. |
| **Shot outcomes — Defined** | Goal, saved, blocked, post/wall or off target. | Follow each classified attempt through contacts, crossings and possession changes. Define precedence for sequences with multiple events. |
| **Shot conversion and accuracy — Defined** | Goals per attempt and on-target attempts per attempt. | Calculate from the unified shot-event set. These ratios are misleading if the denominator contains only the current goal-bound kicks. |
| **Shot distance and angle — Direct once classified** | Geometry of shooting opportunities. | Compute distance to goal and angle subtended by its endpoints, respecting ball radius and stadium geometry. |
| **Shot speed and placement — Direct once classified** | Execution characteristics. | Capture post-kick velocity, speed at goal-line crossing and crossing location relative to the posts. |
| **Key passes / shot assists — Defined** | Passes directly creating attempts. | Link the final completed pass to a subsequent shot in the same possession, under a documented time/action rule. |
| **Shot-creating involvement — Defined** | Contributions earlier in a shooting sequence. | Trace a bounded number of actions or seconds before a shot; identify participating players and action types. |
| **Saves — Defined** | Defensive interventions stopping a goal-bound attempt. | Identify the responsible contact/kick and compare the incoming trajectory with its outcome. Goalkeeper attribution additionally needs a role assignment. |
| **Shot blocks — Defined** | Outfield interventions against attempts. | Use the same intervention detection, distinguishing the defender’s role and location. “Block” versus “save” is partly a convention. |
| **Save percentage — Defined** | Saves relative to eligible attempts faced. | Divide credited saves by saves plus eligible goals conceded, with explicit handling of own goals, deflections and teammate blocks. |
| **Rebound control — Defined** | Whether a save/block leads to retained control or another threat. | Examine the next controller, recovery location and subsequent shot within a defined window. |
| **Goalkeeper positioning and distribution — Defined** | Position relative to goal/ball, sweeping and release effectiveness. | Use an explicit goalkeeper assignment or infer role over time; measure position, recoveries outside a goal area and outcomes of releases. |

A useful HaxBall-specific feature is **wall-assisted shooting**. A straight-line projection misses attempts deliberately banked off walls; the decoded physics lets us model those paths.

## Movement and spatial metrics

| Metric | Description | How to obtain it |
|---|---|---|
| **Distance travelled — Direct** | Movement workload in game units. | Sum successive position displacements during eligible play; exclude spawns, teleports and reset transitions. |
| **Average and peak speed — Direct** | Movement speed profile. | Read velocity or calculate displacement over time. Express in game units/second; metres require an explicit scale. |
| **Acceleration, braking and turns — Direct** | Changes in movement speed and direction. | Differentiate velocity; group changes into episodes and distinguish collision impulses from player-driven movement. |
| **High-speed movement — Defined** | Time/distance above a speed threshold. | Use thresholds relative to the stadium’s achievable movement speed, rather than importing football sprint thresholds. |
| **Movement heatmap — Direct** | Where a player spends active time. | Accumulate occupancy per spatial cell. This already exists. |
| **Conditional heatmaps — Defined** | Positioning in attack, defence, leading or trailing. | Filter occupancy by possession, phase or score state before accumulation. |
| **Average position and spread — Direct** | Typical location and variation around it. | Calculate position mean, median and covariance, preferably separately by possession phase. |
| **Ball proximity and support distance — Direct** | How closely a player follows or supports play. | Track distance to the ball, carrier and nearby teammates; aggregate distributions, not only averages. |
| **Territory / thirds — Direct/Defined** | Where the ball spends time. | Accumulate ball occupancy in normalized zones. Separate total time from time under either team’s control. |
| **Carries/dribbles — Defined** | Advancing while maintaining ball control. | Detect continuous control episodes with meaningful player/ball displacement; measure progress, duration and loss outcome. |
| **Off-ball attacking runs — Defined** | Movement into useful attacking space without controlling the ball. | Detect forward movement relative to the carrier and defence; distinguish a simple forward run from one that improves a passing option. |
| **Recovery runs — Defined** | Movement back into defensive position after a loss. | Identify possession losses and measure retreat speed, distance and time to regain a defined defensive position. |

## Defending, duels and pressing

| Metric | Description | How to obtain it |
|---|---|---|
| **Ball recoveries — Defined** | Establishing control of a loose ball. | Detect loose→controlled transitions; distinguish from taking control directly from an opponent. |
| **Interceptions — Defined** | Cutting out an opponent’s transfer. | Identify opponent release followed by a defender’s intervention/control before an attacking reception. Pass intent remains a classification dependency. |
| **Tackles / dispossessions — Defined** | Taking the ball from an established controller. | Detect contested interaction followed by control transfer; avoid calling every opposing touch a successful tackle. |
| **Duels and duel win rate — Defined** | Outcomes of contested-ball episodes. | Open an episode when opponents can contest the ball; close it on established control, goal or timeout. Allow neutral outcomes. |
| **Clearances — Defined** | Defensive releases moving the ball away from immediate danger. | Combine release location, nearby threat, direction and resulting field position. Intent cannot be known with certainty. |
| **Pressure events — Defined** | Opponents restricting a controller’s options. | Begin with distance and closing speed; improve using estimated time to reach the ball or carrier. |
| **Pressing success — Defined** | Pressure followed by a regain or forced retreat. | Link pressure episodes to subsequent outcomes within a window. Report association, not proof that the press caused the outcome. |
| **Counterpressing — Defined** | Immediate pressure after losing possession. | Detect pressure/regains shortly after a team control loss, using configurable time and location rules. |
| **Dangerous turnovers — Defined/Modelled** | Losses exposing a team to immediate danger. | Start with losses near own goal or with few defenders behind the ball; later weight by change in estimated scoring/conceding probability. |
| **Player collisions and bumps — Direct/Defined** | Contact between players and its effects. | Instrument collision episodes; measure resulting displacement, loss of control or opening of space. Separate collision facts from claims about intent. |

## Team shape and tactical metrics

| Metric | Description | How to obtain it |
|---|---|---|
| **Team width and depth — Direct** | How widely and deeply a team positions itself. | Measure lateral and longitudinal spread, with/without the goalkeeper and by possession phase. |
| **Team centroid and compactness — Direct** | Collective position and cohesion. | Calculate centroid, mean pairwise distance or distance from centroid over active ticks. |
| **Occupied area — Direct** | Geometric area covered by a team. | Compute the convex hull of player positions. Interpret cautiously for small-sided formats. |
| **Defensive line height — Defined** | How high a team defends. | Use longitudinal positions of designated or inferred defensive players; normalize by pitch length. |
| **Players behind the ball — Direct** | Defensive cover at a given moment. | Count players closer to their own goal than the ball in the attacking-axis coordinate system. |
| **Local overloads — Defined** | Numerical superiority around an area. | Compare attacker/defender counts or arrival times within a ball-centred region or receiving zone. |
| **Progression speed / directness — Defined** | How quickly and directly possessions advance. | Divide forward progress by possession duration; compare net progress with total ball movement or number of actions. |
| **Counterattacks — Defined** | Fast attacks after regaining possession. | Detect regains followed by rapid advancement or shots while opposition cover is limited. |
| **Rest defence — Defined** | Defensive protection retained during attacks. | Measure defenders behind the ball, their spacing and their ability to reach likely counterattack lanes while their team attacks. |
| **Kickoff/restart effectiveness — Defined** | Outcomes of scripted restart phases. | Segment kickoff resets; measure retention, progression, shots and goals within a defined phase. Other restart types require ruleset-specific detection. |
| **Territorial dominance / field tilt — Defined** | Relative activity in attacking areas. | Compare controlled time, touches or completed passes in each team’s attacking third. Name the denominator because these are different measures. |

## Advanced metrics

These require more than collecting another counter. Some can begin as transparent geometric estimates; probability-based versions need training and calibration.

| Metric | Description | How to obtain it |
|---|---|---|
| **Expected goals, xG — Modelled** | Probability that a classified opportunity becomes a goal. | Train on HaxBall shot outcomes using distance, angle, ball velocity, defender positions, goal coverage, pressure and preceding actions. Separate pre-shot chance quality from post-shot execution. |
| **Expected assists, xA — Modelled** | Quality of chances directly created by a player. | Under the shot-assisted definition, sum the xG of shots created by their final pass. A model valuing passes that never produce a shot is a different metric and should be named separately. |
| **Post-shot scoring probability — Modelled** | Difficulty of stopping the executed shot. | Model the post-release trajectory, speed, placement, defenders and goalkeeper state. Include wall interactions where relevant. |
| **Goals prevented — Modelled** | Shot-stopping above or below expectation. | For a defined set of eligible attempts faced, subtract actual goals conceded from summed post-shot scoring probabilities. Requires reliable intervention and role attribution. |
| **Expected threat, xT — Modelled** | Value of moving possession into more threatening locations. | Learn zone-level shooting, scoring and movement probabilities from HaxBall possessions; credit movement by the difference between destination and origin value. |
| **Contextual action value / VAEP-style value — Modelled** | Offensive and defensive value of passes, carries, tackles and other actions. | Predict scoring and conceding over a fixed future horizon; value an action by the change in those probabilities before/after it, from a consistent team perspective. |
| **Expected pass completion, xPass — Modelled** | Difficulty of a pass given its context. | Train completion probability from release geometry, receiver movement, opponents, ball speed and wall routes. Compare completion with expectation over sufficient attempts. |
| **Time to intercept — Modelled** | How soon each player could reach a moving ball or target. | Simulate reachable player motion using current velocity, acceleration and collisions; compare with the ball trajectory under stated assumptions about future inputs. |
| **Pitch control — Modelled** | Which team is more likely to control each location. | Evaluate arrival times on a grid, incorporating ball travel, reaction assumptions and control requirements. A nearest-player/Voronoi map is a simpler geometric proxy. |
| **Available passing options — Modelled** | How many useful, reasonably safe releases a carrier has. | Evaluate candidate receivers/targets using ball travel, interception risk and expected control on arrival; score option quality rather than only counting teammates. |
| **Goal-mouth coverage / shooting-window quality — Modelled** | How much of the goal a player can plausibly score into. | Sweep candidate release directions and evaluate disc geometry and defender reach. Static visible angle is a useful first approximation, not a calibrated scoring probability. |
| **Off-ball opportunity value — Modelled** | Credit for creating a dangerous receiving position without touching the ball. | Combine likelihood of delivery, control on arrival and subsequent scoring value; track improvements during runs. |
| **Possession-chain contribution — Defined/Modelled** | Involvement in possessions that generate valuable chances. | Sum shot value for possessions in which a player participated, or allocate value by action. Giving everyone the full chain value produces an involvement metric, not additive individual credit. |
| **On/off and adjusted player impact — Modelled** | Team performance associated with a player after accounting for context. | Across many games, model goal/xG differences with teammates, opponents, stadium and game state; regularize estimates and report uncertainty. |
| **Win probability and action impact — Modelled** | Chance of winning from the current state, and how events change it. | Train on completed comparable games using score, remaining time, format and strength estimates. Truncated recordings cannot simply be labelled as final outcomes. |
| **Counterfactual action comparison — Modelled/simulated** | Compare an actual release with alternative directions or timings. | Clone simulation state and roll out alternative actions under explicitly chosen future-input policies. This answers “under these assumptions,” not what players certainly would have done. |

The football research provides useful frameworks, but **we should train HaxBall versions rather than reuse football coefficients**:

- xG benefits from defender and goalkeeper positioning, which our reconstructed state can supply. [StatsBomb’s explanation](https://blogarchive.statsbomb.com/news/statsbomb-data-case-studies-freeze-frames-and-defender-locations/)
- xT values progression through learned location values. [Original xT explanation](https://karun.in/blog/expected-threat.html)
- VAEP values actions through changes in scoring and conceding probability. [Original paper](https://www.janvanhaaren.be/assets/papers/kdd-2019-vaep.pdf)
- Tracking-based models can assess control and opportunities created without a touch. [Spearman’s research](https://static.hudl.com/craft/downloads/SSAC2018_Beyond_Expected_Goals.pdf?mtime=20180327111214)

## Limitations of the current implementation

The existing [normalization and export logic](src/engine/analyze.js) is a starting point, but these should be addressed before building advanced statistics:

| Current behaviour | Consequence |
|---|---|
| Standard-mode possession follows the last kicker’s team. | It can credit possession while the ball is loose or being physically controlled by an opponent who has not kicked. |
| A standard-mode pass is inferred when a different teammate next kicks. | A reception without another kick can be missed; intervening physical contacts are not fully represented. |
| Shots use a goal-bound trajectory heuristic. | This is not a complete shot-attempt dataset, especially for blocked, off-target or wall-assisted attempts. |
| Several totals are matched by nickname. | Duplicate names or a player changing teams can make attribution ambiguous. |
| Exported event maps lack a complete timestamped action chain. | They cannot reliably support sequences, pressure at release, interceptions or predictive-model training. |
| Heatmaps aggregate positions into cells. | They preserve occupancy, but lose movement order, speed and context. |

These are limitations of the current collectors/export, **not of the replay’s underlying data**.

## Possible implementation approach

First add a common event-and-state collection layer inside the standalone engine:

```text
simulation
  → timed inputs, kicks, contacts, goals and phase changes
  → control episodes and ball-transfer outcomes
  → metric calculators
  → statistics, event maps and timeline links
```

Every event should carry a stable actor ID, team at the time, recording tick, phase, position and relevant before/after velocity. Transfers should link their release and reception/interception events. Ambiguous events should retain a classification/confidence flag.

Most metrics can be accumulated while stepping the replay; we do not need to keep every tick in the exported JSON. Short rolling buffers and event snapshots are enough for many contextual metrics. Accurate contact and motion calculations should use full-resolution simulation, while more expensive tactical surfaces can update less frequently.

Suggested implementation order, subject to later discussion:

1. **Reliable foundations:** IDs, timestamps, successful kicks, physical contacts, phase-aware clocks and control episodes.
2. **Useful base statistics:** recoveries, losses, receptions, passing networks, progressive transfers, carries, distance and conditional heatmaps.
3. **Defensive analysis:** interceptions, duels, pressure, shot outcomes, saves and blocks.
4. **Team analysis:** width/depth, compactness, overloads, transition speed and rest defence.
5. **Predictive metrics:** xG and xA first; then xPass, xT and contextual action value.

For predictive models, split training and evaluation by **whole match/recording**, not individual frames, avoid using future information in input features, and validate separately across stadiums and rulesets.

**The highest-value initial additions would be recoveries, possession losses, passes received, progressive passes, key passes, saves/blocks, and possession-dependent heatmaps.** They would add substantial analytical value without needing a trained model.
