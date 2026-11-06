import { readFile } from 'node:fs/promises';
import { analyzeReplay } from '../src/engine/analyze.js';

const args = process.argv.slice(2);
const path = args.find(arg => arg !== '--frames');
if (!path) {
  console.error('Usage: npm run analyze -- /path/to/replay.hbr2 [--frames]');
  process.exitCode = 2;
} else {
  try {
    const result = analyzeReplay(await readFile(path), { includeFrames: args.includes('--frames') });
    if (!args.includes('--frames')) for (const game of result.games) delete game.frames;
    console.log(JSON.stringify(result, null, 2));
  } catch (error) {
    console.error(error.message);
    process.exitCode = 1;
  }
}
