import React from 'react';
import { render, screen, fireEvent, act } from '@testing-library/react';
import '@testing-library/jest-dom';

// ✅ Mock ESM-only deps BEFORE importing App
jest.mock('remark-gfm', () => ({
  __esModule: true,
  default: () => null,
}));

jest.mock('react-markdown', () => ({
  __esModule: true,
  default: ({ children }) => <div>{children}</div>,
}));

import App from '../App';

function mockFetchSSE(chunks, { ok = true, status = 200 } = {}) {
  const encoder = new TextEncoder();
  let i = 0;

  const reader = {
    read: jest.fn().mockImplementation(async () => {
      if (i >= chunks.length) return { value: undefined, done: true };
      const value = encoder.encode(chunks[i]);
      i += 1;
      return { value, done: false };
    }),
  };

  global.fetch = jest.fn().mockResolvedValue({
    ok,
    status,
    body: {
      getReader: () => reader,
    },
  });

  return reader;
}

describe('Digirett App tests', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  test('shows welcome message', () => {
    render(<App />);
    expect(screen.getByText(/ask me anything about norwegian law/i)).toBeInTheDocument();
  });

  test('renders input box', () => {
    render(<App />);
    expect(screen.getByPlaceholderText(/ask about norwegian law/i)).toBeInTheDocument();
  });

  test('send button disabled initially and enabled after typing', () => {
    render(<App />);
    const button = screen.getByRole('button');
    expect(button).toBeDisabled();

    const input = screen.getByPlaceholderText(/ask about norwegian law/i);
    fireEvent.change(input, { target: { value: 'Hello' } });
    expect(button).not.toBeDisabled();
  });

  test('streams tokens into assistant message and shows sources after complete', async () => {
    const sse = [
      `data: {"type":"sources","data":[{"title":"Aksjeloven","url":"https://lovdata.no","chunk_text":"...","relevance_score":0.9}]}\n\n`,
      `data: {"type":"token","data":"Hello "}\n\n`,
      `data: {"type":"token","data":"world"}\n\n`,
      `data: {"type":"complete","metadata":{"cached":false}}\n\n`,
    ];
    mockFetchSSE(sse);

    render(<App />);

    const input = screen.getByPlaceholderText(/ask about norwegian law/i);
    fireEvent.change(input, { target: { value: 'Test question' } });

    const button = screen.getByRole('button');

    await act(async () => {
      fireEvent.click(button);
    });

    expect(screen.getByText('Test question')).toBeInTheDocument();
    expect(await screen.findByText(/Hello world/i)).toBeInTheDocument();

    // Your UI only renders sources when streaming=false
    expect(await screen.findByText(/Sources/i)).toBeInTheDocument();
    expect(await screen.findByText(/Aksjeloven/i)).toBeInTheDocument();
  });

  test('shows error message on failed HTTP response', async () => {
    global.fetch = jest.fn().mockResolvedValue({ ok: false, status: 500 });

    render(<App />);
    const input = screen.getByPlaceholderText(/ask about norwegian law/i);
    fireEvent.change(input, { target: { value: 'Test' } });

    const button = screen.getByRole('button');

    await act(async () => {
      fireEvent.click(button);
    });

    expect(await screen.findByText(/HTTP 500/i)).toBeInTheDocument();
  });
});
