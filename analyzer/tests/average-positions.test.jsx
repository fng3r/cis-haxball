// @vitest-environment jsdom
import React from 'react';
import { afterEach, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import AveragePositions, { averagePosition } from '../src/components/AveragePositions.jsx';

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

it('weights positions by time and ignores invalid or empty movement data', () => {
  expect(averagePosition({ maps: { heatmap: [
    { x: -100, y: 20, ticks: 3 }, { x: 100, y: 100, ticks: 1 },
    { x: NaN, y: 0, ticks: 10 }, { x: 900, y: 0, ticks: 0 },
    { x: 0, y: Infinity, ticks: 1 }, { x: 0, y: 0, ticks: -1 },
    { x: 0, y: 0, ticks: Infinity },
  ] } })).toEqual({ x: -50, y: 40 });
  expect(averagePosition({})).toBeNull();
  expect(averagePosition({ maps: { heatmap: [] } })).toBeNull();
});

it('groups players by replay side, uses context team identities and positions markers on the pitch', () => {
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(null);
  const game = { stadium: { width: 400, height: 200 }, players: [
    { id: '1:red', nick: 'Alice', team: 'red', maps: { heatmap: [{ x: -200, y: 100, ticks: 10 }] } },
    { id: '2:blue', nick: 'Bob', team: 'blue', maps: { heatmap: [{ x: 100, y: -100, ticks: 10 }] } },
    { id: '3:red', nick: 'Unknown', team: 'red' },
  ] };
  const { rerender } = render(<AveragePositions game={game} redIdentity={{ name: 'Away', logo: '/away.png' }} blueIdentity={{ name: 'Home' }} />);
  const away = screen.getByRole('img', { name: 'Away average positions: Alice' });
  expect(away.querySelector('[title="Alice"]')).toHaveStyle({ left: '25%', top: '75%' });
  const home = screen.getByRole('img', { name: 'Home average positions: Bob' });
  expect(home.querySelector('[title="Bob"]')).toHaveStyle({ left: '62.5%', top: '25%' });
  expect(screen.queryByTitle('Unknown')).not.toBeInTheDocument();
  rerender(<AveragePositions game={{ ...game, players: [] }} />);
  expect(screen.getAllByText('No movement data for this team.')).toHaveLength(2);
  expect(screen.queryByRole('img')).not.toBeInTheDocument();
});
