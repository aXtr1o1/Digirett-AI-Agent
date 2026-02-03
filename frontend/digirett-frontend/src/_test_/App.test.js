import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom';
import App from '../App';

// prevent ESM crash
jest.mock('react-markdown', () => () => <div />);

describe('Digirett App basic tests', () => {

  test('shows welcome message', () => {
    render(<App />);
    expect(
      screen.getByText(/ask me anything about norwegian law/i)
    ).toBeInTheDocument();
  });

  test('renders input box', () => {
    render(<App />);
    expect(
      screen.getByPlaceholderText(/ask about norwegian law/i)
    ).toBeInTheDocument();
  });

  test('send button is disabled initially', () => {
    render(<App />);
    expect(screen.getByRole('button')).toBeDisabled();
  });

  test('typing works in input field', () => {
    render(<App />);
    const input = screen.getByPlaceholderText(/ask about norwegian law/i);
    fireEvent.change(input, { target: { value: 'Hello' } });
    expect(input.value).toBe('Hello');
  });
  test('send button is enabled when input has text', () => {
    render(<App />);
    const input = screen.getByPlaceholderText(/ask about norwegian law/i);
    const button = screen.getByRole('button');

    fireEvent.change(input, { target: { value: 'Test query' } });

    expect(button).toBeEnabled();
  });

  test('user message is rendered after clicking send', async () => {
    render(<App />);

    const input = screen.getByPlaceholderText(/ask about norwegian law/i);
    const button = screen.getByRole('button');

    fireEvent.change(input, { target: { value: 'Hello law' } });
    fireEvent.click(button);

    expect(await screen.findByText('Hello law')).toBeInTheDocument();
  });

  test('input field is cleared after sending message', () => {
    render(<App />);

    const input = screen.getByPlaceholderText(/ask about norwegian law/i);
    const button = screen.getByRole('button');

    fireEvent.change(input, { target: { value: 'Clear me' } });
    fireEvent.click(button);

    expect(input.value).toBe('');
  });
});
