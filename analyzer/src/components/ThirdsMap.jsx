import { useEffect, useRef } from 'react';
import { classic } from '../../legacy/src/vendor/classic.js';
import { drawStadium } from './stadium.js';

const LABELS = ['Red third', 'Middle', 'Blue third'];

export default function ThirdsMap({ game }) {
  const canvas = useRef(null);
  const stadium = game.stadium || classic;
  const total = game.thirds.reduce((sum, count) => sum + count, 0);
  const percentages = game.thirds.map(count => Math.round(count / (total || 1) * 100));
  const halfWidth = stadium.bg?.width || stadium.width;
  const halfHeight = stadium.bg?.height || stadium.height;
  useEffect(() => {
    const ctx = canvas.current.getContext('2d');
    if (ctx) drawStadium(ctx, stadium);
  }, [stadium]);

  return <div className="relative mx-auto max-w-3xl overflow-hidden rounded-box">
    <canvas ref={canvas} width="1000" height="500" role="img" aria-label={`Ball territory: ${LABELS.map((label, i) => `${label} ${percentages[i]}%`).join(', ')}`} className="block h-auto w-full" />
    <div aria-hidden="true" className="absolute grid grid-cols-3" style={{
      left: `${(stadium.width - halfWidth) / (2 * stadium.width) * 100}%`,
      top: `${(stadium.height - halfHeight) / (2 * stadium.height) * 100}%`,
      width: `${halfWidth / stadium.width * 100}%`,
      height: `${halfHeight / stadium.height * 100}%`,
    }}>
      {LABELS.map((label, i) => <div key={label} className={`flex min-w-0 items-center justify-center ${i === 0 ? 'bg-error/25' : i === 2 ? 'border-l border-dashed border-base-content/50 bg-info/25' : 'border-l border-dashed border-base-content/50 bg-base-200/15'}`}>
        <div className="rounded-field bg-base-100/90 px-2 py-2 text-center shadow-sm sm:px-3">
          <span className="block font-mono text-lg font-semibold sm:text-2xl">{percentages[i]}%</span>
          <span className="mt-1 block text-[10px] text-base-content/70 sm:text-xs">{label}</span>
        </div>
      </div>)}
    </div>
  </div>;
}
