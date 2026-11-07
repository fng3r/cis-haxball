let nativeController;
let nativeResources;
let nativeGoalControls;
let nativeGameSync;

function saveNativeCheckpoint(replay) {
  const writer = w.ha();
  replay.T.ga(writer);
  return { tick: replay.Y, data: Uint8Array.from(writer.Sb()),
    offset: replay.checkpointEventOffset, baseTick: replay.checkpointEventBaseTick };
}

function restoreNativeCheckpoint(replay, checkpoint) {
  const data = checkpoint.data;
  replay.T.ja(new F(new DataView(data.buffer, data.byteOffset, data.byteLength)));
  replay.Y = checkpoint.tick;
  replay.Lc.a = checkpoint.offset;
  replay.hg = checkpoint.baseTick;
  replay.Dl();
}

async function prepareNativeResources() {
  if (!nativeResources) {
    nativeResources = (async () => {
      kc.fj();
      const response = await fetch(`${import.meta.env.BASE_URL}player/res.dat`, { signal: AbortSignal.timeout(15000) });
      if (!response.ok) throw new Error('Could not load native replay player resources.');
      const zip = new window.JSZip(await response.arrayBuffer());
      n.Na = new Ub(zip);
      [n.Ko, n.Vn, n.Tn, n.Dm] = await Promise.all(
        ['grass', 'concrete', 'concrete2', 'typing'].map(name => x.Wg(zip.file(`images/${name}.png`).asArrayBuffer())),
      );
      await n.Na.ro;
      document.addEventListener('pointerdown', () => n.Na.Tl(), { once: true });
    })();
  }
  return nativeResources;
}

export async function openNativeReplay(bytes) {
  await prepareNativeResources();
  nativeController?.ia();
  // Analysis happens in the separate worker. Playback must not collect stats
  // or run the analyzer's old fast-forward/reset completion heuristic.
  keepUpdating = false;
  playSounds = false;
  loading = { done: true };
  x.Pg = document.getElementById('player');
  x.Pg.replaceChildren();
  const replay = new Jb(new Uint8Array(bytes), new fa, 3);
  const { checkpoints, chatEntries } = prepareReplayCheckpoints(replay, saveNativeCheckpoint);
  restoreNativeCheckpoint(replay, checkpoints[0]);
  replay.Qb = replay.sk = 0;
  replay.Wh = window.performance.now();
  mountCheckpointSeek(replay, checkpoints, restoreNativeCheckpoint);
  playSounds = true;
  nativeController = new Vb(replay);
  mountFitPitch(nativeController);
  const instructions = nativeController.j.g.querySelector('.chatbox-view [data-hook=log] > p');
  instructions?.remove();
  // Open each recording with the entire field visible. Native view shortcuts
  // and Settings still select the original fixed zoom modes.
  n.A.Tb.Xa(-1);
  setNativePlayIcon(nativeController.je.g.querySelector('[data-hook=playicon]'), false);
  nativeGoalControls = mountGoalControls(nativeController.je, replay, seekNativeReplay, tick => notify('goal', tick));
  nativeGameSync = mountGameSync(nativeController.je, replay, index => notify('game', index));
  mountChatSync(nativeController.je, replay, nativeController.j.Qa, chatEntries);
  nativeController.je.de = () => {
    nativeController.ia();
    nativeController = null;
    x.Pg.replaceChildren();
    notify('closed');
  };
  nativeController.j.me(false);
  x.Pg.appendChild(nativeController.j.g);
  document.getElementById('status').hidden = true;
}

export function setNativeGoals(ticks) { nativeGoalControls?.setGoals(ticks); }
export function setNativeGames(starts) { nativeGameSync?.setGames(starts); }
export function seekNativeGoal(tick) { nativeGoalControls?.seekGoal(tick); }

export function seekNativeReplay(tick) {
  if (!nativeController) return;
  const replay = nativeController.ya;
  replay.er(Math.max(0, Math.min(replay.mf, tick)) * replay.mh);
  const controls = nativeController.je;
  if (!controls.Wf) {
    controls.Wf = true;
    controls.Vp();
    controls.el();
  }
}

export function replayHotkey(action) {
  if (!nativeController) return false;
  if (action === 'toggle-focus') {
    notify('toggle-focus');
  } else if (action === 'previous-goal' || action === 'next-goal') {
    nativeController.je.g.querySelector(action === 'previous-goal' ? '[aria-label="Previous goal"]' : '[aria-label="Next goal"]').click();
  } else if (action === 'reset-zoom') {
    n.A.Tb.Xa(-1);
  } else if (action === 'toggle') {
    nativeController.je.g.querySelector('[data-hook=play]').click();
  } else if (action === 'faster' || action === 'slower') {
    nativeController.je.g.querySelector(action === 'faster' ? '[data-hook=spdup]' : '[data-hook=spddn]').click();
  } else if (action === 'backward' || action === 'forward') {
    const replay = nativeController.ya;
    const position = (replay.Fd > 0 ? replay.Fd : replay.Qb) / replay.mh;
    seekNativeReplay(position + (action === 'forward' ? 300 : -300));
  } else return false;
}
