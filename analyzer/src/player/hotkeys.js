// Shared by the workspace and iframe so shortcuts work with either focused.
export function mountReplayHotkeys(target, dispatch) {
  function onKeyDown(event) {
    if (event.defaultPrevented || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
    if (event.target?.closest?.('input, textarea, select, [contenteditable]:not([contenteditable="false"]), [role="slider"], [role="textbox"]')) return;
    const action = { ArrowLeft: 'backward', ArrowRight: 'forward', ' ': 'toggle' }[event.key];
    if (!action) return;
    // Let Space activate focused buttons and links normally.
    if (action === 'toggle' && event.target?.closest?.('button, a, [role="button"]')) return;
    if (action === 'toggle' && event.repeat) { event.preventDefault(); return; }
    if (dispatch(action) === false) return;
    event.preventDefault();
  }
  target.addEventListener('keydown', onKeyDown);
  return () => target.removeEventListener('keydown', onKeyDown);
}
