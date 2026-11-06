export function serializeStats(replay) {
  // Spatial analysis belongs in exports; omit only diagnostic playback frames.
  return JSON.stringify(replay, (key, value) => key === 'frames' ? undefined : value, 2);
}
