// @vitest-environment jsdom
import React from 'react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import ReplayLinkForm from '../src/components/ReplayLinkForm.jsx';
import { fetchThehaxReplay } from '../src/external-replay.js';
vi.mock('../src/external-replay.js', () => ({ fetchThehaxReplay: vi.fn() }));
beforeEach(() => {
  HTMLDialogElement.prototype.showModal = function () { this.open = true; };
  HTMLDialogElement.prototype.close = function () { this.open = false; this.dispatchEvent(new Event('close')); };
});
afterEach(() => { cleanup(); vi.resetAllMocks(); });
function open(onFiles = vi.fn()) {
  render(<ReplayLinkForm onFiles={onFiles} />);
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Use replay links' }));
  expect(screen.getByRole('dialog', { name: 'Analyze replay links' })).toBeInTheDocument();
  return onFiles;
}
function submit(value) {
  fireEvent.change(screen.getByLabelText('Replay links'), { target: { value } });
  fireEvent.submit(screen.getByRole('form', { name: 'Open replay links' }));
}
it('downloads multiple unique links in order and queues each file, then closes', async () => {
  const first = new File(['replay'], 'first.hbr2'), second = new File(['replay'], 'second.hbr2');
  fetchThehaxReplay.mockResolvedValueOnce(first).mockResolvedValueOnce(second);
  const onFiles = open();
  submit('https://replay.thehax.pl/first\nhttps://replay.thehax.pl/second\nhttps://replay.thehax.pl/first');
  await waitFor(() => expect(onFiles).toHaveBeenCalledTimes(2));
  expect(onFiles.mock.calls).toEqual([[[first]], [[second]]]);
  expect(fetchThehaxReplay).toHaveBeenCalledTimes(2);
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
});
it('keeps failed links for retry without adding successful files again', async () => {
  const file = new File(['replay'], 'good.hbr2');
  fetchThehaxReplay.mockRejectedValueOnce(new Error('Replay removed.')).mockResolvedValueOnce(file);
  const onFiles = open(); submit('https://replay.thehax.pl/bad\nhttps://replay.thehax.pl/good');
  await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Replay removed.'));
  expect(onFiles).toHaveBeenCalledWith([file]);
  expect(screen.getByLabelText('Replay links')).toHaveValue('https://replay.thehax.pl/bad');
  fetchThehaxReplay.mockResolvedValueOnce(file);
  fireEvent.click(screen.getByRole('button', { name: 'Analyze' }));
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  expect(fetchThehaxReplay).toHaveBeenCalledTimes(3);
});
it('cancels downloads on modal close without starting remaining links', async () => {
  fetchThehaxReplay.mockImplementationOnce((_, { signal }) => new Promise((resolve, reject) => signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')))));
  const onFiles = open(); submit('https://replay.thehax.pl/first\nhttps://replay.thehax.pl/second');
  fireEvent.click(screen.getByRole('button', { name: 'Cancel downloads' }));
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  expect(onFiles).not.toHaveBeenCalled(); expect(fetchThehaxReplay).toHaveBeenCalledTimes(1);
});
it('rejects an empty submission without downloading', () => {
  open(); submit('  ');
  expect(screen.getByRole('alert')).toHaveTextContent('Enter at least one replay link.');
  expect(fetchThehaxReplay).not.toHaveBeenCalled();
});
