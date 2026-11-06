// Shared by the workspace and iframe so shortcuts work with either focused.
export function mountReplayHotkeys(target, dispatch) {
  function onKeyDown(event) {
    if (target.document?.querySelector('dialog[open]')) return;
    if (event.defaultPrevented || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
    if (event.target?.closest?.('input, textarea, select, [contenteditable]:not([contenteditable="false"]), [role="slider"], [role="textbox"]')) return;
    const action = { ArrowLeft: 'backward', ArrowRight: 'forward', ArrowUp: 'faster', ArrowDown: 'slower', ' ': 'toggle', '0': 'reset-zoom', f: 'toggle-focus', '[': 'previous-goal', ']': 'next-goal' }[event.key === 'F' ? 'f' : event.key];
    if (!action) return;
    // Let Space activate focused buttons and links normally.
    if (action === 'toggle' && event.target?.closest?.('button, a, [role="button"]')) return;
    if (['toggle', 'toggle-focus'].includes(action) && event.repeat) { event.preventDefault(); return; }
    if (dispatch(action) === false) return;
    event.preventDefault();
  }
  target.addEventListener('keydown', onKeyDown);
  return () => target.removeEventListener('keydown', onKeyDown);
}
