export function chatEndAt(entries, tick) {
  let lo = 0, hi = entries.length;
  while (lo < hi) {
    const mid = (lo + hi) >>> 1;
    if (entries[mid].tick <= tick) lo = mid + 1;
    else hi = mid;
  }
  return lo;
}

function messageNode(entry, document) {
  const node = document.createElement('p');
  node.textContent = entry.text;
  if (entry.type === 'notice') node.className = 'notice';
  if (entry.type === 'announcement') {
    node.className = 'announcement';
    if (Number.isInteger(entry.color) && entry.color >= 0) node.style.color = `#${(entry.color & 0xffffff).toString(16).padStart(6, '0')}`;
    if ([1, 4].includes(entry.style)) node.style.fontWeight = 'bold';
    if ([2, 5].includes(entry.style)) node.style.fontStyle = 'italic';
    if ([3, 4, 5].includes(entry.style)) node.style.fontSize = '12px';
  }
  return node;
}

export function mountChatSync(controls, replay, chat, entries) {
  const log = chat.dc;
  // Native callbacks continue handling sounds/UI, but cannot append duplicate rows.
  chat.ba = chat.Gb = chat.pp = () => {};
  let end = -1;
  function sync(force = false) {
    const tick = (replay.Fd > 0 ? replay.Fd : replay.Qb) / replay.mh;
    const next = chatEndAt(entries, tick);
    if (!force && next === end) return;
    const follow = force || end < 0 || next < end || log.scrollTop + log.clientHeight >= log.scrollHeight - log.clientHeight / 2;
    const first = Math.max(0, next - 100);
    if (force || next < end || end < first) {
      log.replaceChildren(...entries.slice(first, next).map(entry => messageNode(entry, log.ownerDocument)));
    } else {
      for (let i = Math.max(0, end); i < next; i++) log.appendChild(messageNode(entries[i], log.ownerDocument));
      while (log.childElementCount > 100) log.firstElementChild.remove();
    }
    end = next;
    if (follow) log.scrollTop = log.scrollHeight;
  }
  for (const name of ['er', 'ui']) {
    const original = replay[name];
    replay[name] = function (...args) {
      const result = original.apply(this, args);
      sync(true);
      return result;
    };
  }
  const refresh = controls.C;
  controls.C = function (...args) { const result = refresh.apply(this, args); sync(); return result; };
  log.replaceChildren();
  sync(true);
}
