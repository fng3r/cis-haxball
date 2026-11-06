import { useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';

const SHORTCUTS = [
  [['Space'], 'Pause / resume'],
  [['←', '→'], 'Seek backward / forward 5 seconds'],
  [['↑', '↓'], 'Increase / decrease playback speed'],
  [['0'], 'Restore fit-pitch view'],
  [['1', '2', '3', '4'], 'Native zoom modes (player focused)'],
  [['Esc'], 'Exit focus mode; otherwise toggle menu in player'],
  [['?'], 'Open this reference'],
];

export default function KeyboardShortcuts() {
  const dialog = useRef(null);
  const open = () => dialog.current.showModal();
  useEffect(() => {
    const keydown = event => {
      if (event.key !== '?' || event.ctrlKey || event.metaKey || event.altKey || event.defaultPrevented) return;
      if (event.target?.closest?.('input, textarea, select, [contenteditable]:not([contenteditable="false"])') || document.querySelector('dialog[open]')) return;
      event.preventDefault(); open();
    };
    const message = event => {
      const frame = document.querySelector('iframe[title="Original HaxBall replay player"]');
      if (event.origin === location.origin && frame && event.source === frame.contentWindow && event.data?.source === 'haxball-native-player' && event.data.type === 'shortcuts') open();
    };
    window.addEventListener('keydown', keydown);
    window.addEventListener('message', message);
    return () => { window.removeEventListener('keydown', keydown); window.removeEventListener('message', message); };
  }, []);
  return <>
    <button type="button" className="btn btn-sm btn-square" aria-label="Keyboard shortcuts" title="Keyboard shortcuts (?)" onClick={open}>?</button>
    {createPortal(<dialog ref={dialog} className="modal" aria-labelledby="shortcuts-title">
      <div className="modal-box">
        <h2 id="shortcuts-title" className="text-lg font-semibold">Keyboard shortcuts</h2>
        <dl className="mt-5 space-y-4">{SHORTCUTS.map(([keys, description]) => <div key={description} className="flex items-center justify-between gap-4">
          <dt className="flex shrink-0 gap-1">{keys.map(key => <kbd key={key} className="kbd kbd-sm">{key}</kbd>)}</dt>
          <dd className="text-right text-sm text-base-content/75">{description}</dd>
        </div>)}</dl>
        <p className="mt-5 text-xs text-base-content/55">Playback shortcuts work on the page and inside the player. Text fields keep their normal keyboard behavior. Space activates a focused button.</p>
        <form method="dialog" className="modal-action"><button className="btn">Close</button></form>
      </div>
      <form method="dialog" className="modal-backdrop"><button aria-label="Close keyboard shortcuts">close</button></form>
    </dialog>, document.body)}
  </>;
}
