import { readFile, writeFile, mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { createHash } from 'node:crypto';
import assert from 'node:assert/strict';

// Test the native decoder/physics without importing browser UI or bundling
// another production runtime. Use the production checkpoint codec verbatim.
export async function nativeReplayFixture() {
  const original = await readFile(new URL('../legacy/src/game2.js', import.meta.url), 'utf8');
  assert.equal(createHash('sha256').update(original).digest('hex'), 'c5047a4f807a9130bd985f94781c77f22617ea9108b7a97f5e96499ff3b0c81c');
  let source = original.slice(original.indexOf('var kicker, lastKicker')).replace(/export /g, '').replace(/u\.qp\(\)\s*$/, '');
  source = source.replace('  Dl: function () {\n    var a = this.Lc;', '  Dl: function () {\n    this.checkpointEventOffset = this.Lc.a;\n    this.checkpointEventBaseTick = this.hg;\n    var a = this.Lc;');
  const adapter = await readFile(new URL('../src/player/native-adapter.inc', import.meta.url), 'utf8');
  const codec = adapter.slice(adapter.indexOf('function saveNativeCheckpoint'), adapter.indexOf('async function prepareNativeResources'));
  const directory = await mkdtemp(join(tmpdir(), 'native-replay-test-'));
  const file = join(directory, 'runtime.mjs');
  await writeFile(file, `export function create(bytes, inflateRaw) { const pako={inflateRaw};const window={performance:{now:()=>0}};const loading={done:true};\n${source}\n${codec}\nkeepUpdating=false;playSounds=false;kc.fj();return {replay:new Jb(bytes,new fa,3),save:saveNativeCheckpoint,restore:restoreNativeCheckpoint};}`);
  const { create } = await import(pathToFileURL(file));
  return { create, dispose: () => rm(directory, { recursive: true, force: true }) };
}
