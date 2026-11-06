// @vitest-environment jsdom
import React from 'react';
import { afterEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import ReplayLinkForm from '../src/components/ReplayLinkForm.jsx';
import { fetchThehaxReplay } from '../src/external-replay.js';
vi.mock('../src/external-replay.js', () => ({ fetchThehaxReplay: vi.fn() }));
afterEach(() => { cleanup(); vi.resetAllMocks(); });
it('adds downloaded files to the existing queue', async () => {
  const file = new File(['replay'], 'thehax-test.hbr2');
  fetchThehaxReplay.mockResolvedValue(file);
  const onFiles = vi.fn(); render(<ReplayLinkForm onFiles={onFiles} />);
  fireEvent.change(screen.getByLabelText('Replay link'), { target: { value: 'https://replay.thehax.pl/test' } });
  fireEvent.submit(screen.getByRole('form', { name: 'Open replay link' }));
  await waitFor(() => expect(onFiles).toHaveBeenCalledWith([file]));
  expect(screen.getByLabelText('Replay link')).toHaveValue('');
});
it('shows download errors and cancels requests without adding a recording', async () => {
  fetchThehaxReplay.mockRejectedValueOnce(new Error('Replay removed.'));
  const onFiles = vi.fn(); render(<ReplayLinkForm onFiles={onFiles} />);
  const form = screen.getByRole('form', { name: 'Open replay link' });
  fireEvent.submit(form);
  await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Replay removed.'));
  fetchThehaxReplay.mockImplementationOnce((_, { signal }) => new Promise((resolve, reject) => signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')))));
  fireEvent.submit(form);
  fireEvent.click(screen.getByRole('button', { name: 'Cancel download' }));
  await waitFor(() => expect(screen.getByRole('button', { name: 'Analyze link' })).toBeInTheDocument());
  expect(onFiles).not.toHaveBeenCalled();
  expect(screen.queryByRole('alert')).not.toBeInTheDocument();
});
