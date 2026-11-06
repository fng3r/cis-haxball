import { readFile, writeFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';

const root = new URL('../', import.meta.url);
let source = await readFile(new URL('legacy/src/game2.js', root), 'utf8');
if (createHash('sha256').update(source).digest('hex') !== 'c5047a4f807a9130bd985f94781c77f22617ea9108b7a97f5e96499ff3b0c81c') {
  throw new Error('Upstream player changed; review the player integration.');
}
source = source.replace("import './vendor/pako-jszip.min.js';", "import '../../legacy/src/vendor/pako-jszip.min.js';");
source = source.replace(/^import .* from '\.\/components\/(Home|Modal)(\.js)?';$/gm, '');
source = source.replace(/u\.qp\(\)\s*$/, '');
// Only initialize the native transport at paused 1x. Leave its RAF loop,
// interpolation, rendering, seek implementation, and controls unchanged.
source = source.replace('var e = !0,\n    f = 8,', 'var e = !1,\n    f = 2,');
source = source.replace("e ? k.innerHTML = '⏸' : k.innerHTML = '⏵';", 'setNativePlayIcon(k, e);');
const adapter = await readFile(new URL('src/player/native-adapter.inc', root), 'utf8');
await writeFile(new URL('src/player/vendor-player.js', root),
  '// Generated from the original game2.js; see legacy/LICENSE.MD and upstream.json.\n' +
  'import { setNativePlayIcon } from "./play-icon.js";\n' +
  'import { mountGoalControls } from "./goal-controls.js";\n' +
  'import { mountGameSync } from "./game-sync.js";\n' +
  'const notify = (type, message) => parent.postMessage({ source: "haxball-native-player", type, message }, location.origin);\n' +
  'const showStats = () => notify("stats");\n' +
  'const setGameStats = () => {}; const dispatchPlayerList = () => {}; const dispatchPlayerPos = () => {};\n' +
  'const dispatchClearStats = () => {}; const sendSocketMessage = () => {};\n' +
  'const openModal = message => notify("error", message);\n' +
  source + '\n' + adapter);
