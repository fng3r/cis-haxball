// Scores and goal ticks are native replay events, not heuristic player attribution.
// Original-engine metrics below are regression baselines, not manually annotated truth.
export const replayCases = [
  {
    file: 'futsal.hbr2', ticks: 32507, stadium: 'Futsal 3x3 4x4', scores: [[1, 7]],
    goalTicks: [[11912, 13113, 16505, 19636, 20261, 26008, 29865, 31293]],
    original: [{ gameTicks: 28800, kicks: [194, 252], passes: [62, 77], shots: [6, 15], possession: [13332, 15469], thirds: [12671, 8422, 7708] }],
  },
  {
    file: 'futsal-multi.hbr2', ticks: 66686, stadium: 'Futsal 3x3 4x4',
    scores: [[3, 2], [7, 0]],
    goalTicks: [[3996, 4719, 11519, 24063, 28898], [34767, 38149, 48411, 50414, 55332, 58328, 59941]],
    original: [
      { gameTicks: 28800, kicks: [208, 219], passes: [74, 61], shots: [8, 17], possession: [15032, 13769], thirds: [12156, 8636, 8009] },
      { gameTicks: 28800, kicks: [227, 233], passes: [71, 77], shots: [17, 21], possession: [15732, 13008], thirds: [10632, 8882, 9287] },
    ],
  },
  {
    file: 'cis5.hbr2', ticks: 31513, stadium: 'BFF Big v4', scores: [[3, 3]],
    goalTicks: [[4146, 11856, 13258, 16272, 24226, 26154]],
    original: [{ gameTicks: 29095, kicks: [194, 279], passes: [47, 94], shots: [7, 10], possession: [12171, 16925], thirds: [9983, 10373, 8740] }],
  },
  {
    file: 'cis4.hbr2', ticks: 35877, stadium: 'BFF Big v4', scores: [[2, 12]],
    goalTicks: [[7835, 11261, 13414, 17786, 18538, 20029, 22628, 24255, 26556, 27887, 29553, 30280, 32089, 35195]],
    original: [{ gameTicks: 28800, kicks: [237, 220], passes: [65, 95], shots: [6, 10], possession: [13430, 15364], thirds: [9241, 9863, 9697] }],
  },
];
