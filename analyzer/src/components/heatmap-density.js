// A shared density scale for both teams. Color encodes occupancy, not team.
export const HEAT_COLORS = ['#3456bc', '#0bbfc5', '#f3df43', '#f3912b', '#df2929'];

export function densityPixels(cells, stadium, width = 250, height = 125) {
  const field = new Float32Array(width * height);
  const pixels = new Uint8ClampedArray(width * height * 4);
  const sx = width / (2 * stadium.width), sy = height / (2 * stadium.height);
  const sigmaX = Math.max(1, 18 * sx), sigmaY = Math.max(1, 18 * sy);
  for (const cell of cells) {
    if (!Number.isFinite(cell.x) || !Number.isFinite(cell.y) || !(cell.ticks > 0)) continue;
    const cx = (cell.x + stadium.width) * sx, cy = (cell.y + stadium.height) * sy;
    for (let y = Math.max(0, Math.floor(cy - sigmaY * 3)); y <= Math.min(height - 1, Math.ceil(cy + sigmaY * 3)); y++) {
      for (let x = Math.max(0, Math.floor(cx - sigmaX * 3)); x <= Math.min(width - 1, Math.ceil(cx + sigmaX * 3)); x++) {
        const distance = ((x - cx) / sigmaX) ** 2 + ((y - cy) / sigmaY) ** 2;
        field[y * width + x] += cell.ticks * Math.exp(-distance / 2);
      }
    }
  }
  const occupied = [...field].filter(value => value > 0).sort((a, b) => a - b);
  if (!occupied.length) return { width, height, pixels };
  // Resist one stationary outlier washing out the rest of the player's map.
  const reference = occupied[Math.floor((occupied.length - 1) * 0.98)];
  const colors = HEAT_COLORS.map(hex => [1, 3, 5].map(offset => parseInt(hex.slice(offset, offset + 2), 16)));
  for (let i = 0; i < field.length; i++) {
    const value = Math.min(1, field[i] / reference);
    if (value < 0.025) continue;
    const position = value * (colors.length - 1);
    const index = Math.min(colors.length - 2, Math.floor(position));
    const fraction = position - index;
    for (let channel = 0; channel < 3; channel++) {
      pixels[i * 4 + channel] = colors[index][channel] * (1 - fraction) + colors[index + 1][channel] * fraction;
    }
    pixels[i * 4 + 3] = Math.round((0.2 + 0.65 * Math.sqrt(value)) * 255);
  }
  return { width, height, pixels };
}

export function drawDensity(ctx, stadium, cells) {
  const { width, height, pixels } = densityPixels(cells, stadium);
  const overlay = ctx.canvas.ownerDocument.createElement('canvas');
  overlay.width = width; overlay.height = height;
  const layer = overlay.getContext('2d');
  const image = layer.createImageData(width, height);
  image.data.set(pixels);
  layer.putImageData(image, 0, 0);
  ctx.save();
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.imageSmoothingEnabled = true;
  ctx.drawImage(overlay, 0, 0, ctx.canvas.width, ctx.canvas.height);
  ctx.restore();
}
