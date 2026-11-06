import { useEffect, useRef, useState } from 'react';
import { MAX_FILE_BYTES } from './engine/analyze.js';

export function useReplayLibrary({ engine = 'legacy' } = {}) {
  const [recordings, setRecordings] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const running = useRef(null);

  function stopJob() {
    const job = running.current;
    running.current = null;
    if (job) { clearTimeout(job.timeout); job.worker?.terminate(); }
  }
  useEffect(() => () => stopJob(), []);

  useEffect(() => {
    if (running.current) return;
    const recording = recordings.find(item => item.status === 'queued');
    if (!recording) return;
    const job = { id: recording.id };
    running.current = job;
    const update = patch => setRecordings(items => items.map(item => item.id === job.id ? { ...item, ...patch } : item));
    function finish(patch) {
      if (running.current !== job) return;
      stopJob();
      update(patch);
    }
    update({ status: 'analyzing', progress: 0 });
    try {
      job.worker = engine === 'v2'
        ? new Worker(new URL('./engine-v2/analyze.worker.js', import.meta.url), { type: 'module' })
        : new Worker(new URL('./engine/analyze.worker.js', import.meta.url), { type: 'module' });
    } catch {
      finish({ status: 'error', error: 'The analyzer could not start. Use a browser with Web Worker support.' });
      return;
    }
    job.timeout = setTimeout(() => finish({ status: 'error', error: 'Analysis took longer than two minutes. Try a shorter recording.' }), 120_000);
    job.worker.onmessage = ({ data }) => {
      if (running.current !== job) return;
      if (data.type === 'progress') update({ progress: data.progress });
      if (data.type === 'error') finish({ status: 'error', error: data.message });
      if (data.type === 'result') finish({ status: 'ready', progress: 100, result: data.result });
    };
    job.worker.onerror = event => {
      event.preventDefault();
      finish({ status: 'error', error: 'The analyzer could not start. Reload the page and try again.' });
    };
    (async () => {
      try {
        const buffer = await recording.file.arrayBuffer();
        if (running.current === job) job.worker.postMessage(buffer, [buffer]);
      } catch {
        finish({ status: 'error', error: 'Could not read the recording. Choose the file again.' });
      }
    })();
  }, [recordings, engine]);

  function addFiles(files, { selectFirst = true } = {}) {
    const errors = [], added = [];
    for (const file of Array.from(files || [])) {
      if (!file.name.toLowerCase().endsWith('.hbr2')) {
        errors.push(`${file.name}: choose a HaxBall recording with the .hbr2 extension.`);
      } else if (file.size > MAX_FILE_BYTES) {
        errors.push(`${file.name}: choose a recording smaller than 32 MB.`);
      } else {
        added.push({ id: crypto.randomUUID(), file, status: 'queued', progress: 0 });
      }
    }
    if (added.length) {
      setRecordings(items => [...items, ...added]);
      setSelectedId(current => selectFirst ? added[0].id : current || added[0].id);
    }
    return errors;
  }
  function cancel() {
    stopJob();
    setRecordings(items => items.map(item => ['queued', 'analyzing'].includes(item.status) ? { ...item, status: 'cancelled' } : item));
  }
  function clear() {
    stopJob();
    setRecordings([]);
    setSelectedId(null);
  }
  function remove(id) {
    if (running.current?.id === id) stopJob();
    setRecordings(items => items.filter(item => item.id !== id));
    setSelectedId(current => current === id ? recordings.find(item => item.id !== id)?.id || null : current);
  }
  function retry(id) {
    setRecordings(items => items.map(item => item.id === id && ['error', 'cancelled'].includes(item.status) ? { ...item, status: 'queued', error: null, progress: 0 } : item));
  }
  return {
    recordings, recording: recordings.find(item => item.id === selectedId) || null,
    active: recordings.find(item => item.status === 'analyzing'),
    addFiles, cancel, clear, remove, retry, select: setSelectedId,
  };
}
