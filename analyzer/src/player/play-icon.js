export function setNativePlayIcon(icon, playing) {
  // Use vectors instead of Unicode media glyphs, which are missing in some fonts.
  const shape = playing
    ? '<path d="M2 1h3v10H2zm5 0h3v10H7z"/>'
    : '<path d="M2 1l9 5-9 5z"/>';
  icon.innerHTML = `<svg width="12" height="12" viewBox="0 0 12 12" fill="currentColor" aria-hidden="true">${shape}</svg>`;
  icon.closest('button').setAttribute('aria-label', playing ? 'Pause replay' : 'Play replay');
}
