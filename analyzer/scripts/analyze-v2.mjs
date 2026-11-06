import { readFile } from 'node:fs/promises';
import { analyzeReplay } from '../src/engine-v2/analyze.js';
const args = process.argv.slice(2), path = args.find(arg => !arg.startsWith('--'));
if (!path || args.some(arg => arg.startsWith('--') && !['--tracking', '--no-events'].includes(arg))) {
  console.error('Usage: npm run analyze:v2 -- /path/to/replay.hbr2 [--tracking] [--no-events]');
  process.exitCode = 2;
} else {
  try {
    console.log(JSON.stringify(analyzeReplay(await readFile(path), { includeTracking: args.includes('--tracking'), includeEvents: !args.includes('--no-events') }), null, 2));
  } catch (error) { console.error(error.message); process.exitCode = 1; }
}
