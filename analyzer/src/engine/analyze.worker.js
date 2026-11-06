import { analyzeReplay } from './analyze.js';

self.onmessage = ({ data }) => {
  try {
    const result = analyzeReplay(data, { onProgress: progress => self.postMessage({ type: 'progress', progress }) });
    self.postMessage({ type: 'result', result });
  } catch (error) {
    self.postMessage({ type: 'error', message: error.message || 'Could not analyze this recording.' });
  }
};
