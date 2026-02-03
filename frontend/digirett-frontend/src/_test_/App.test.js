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
    const button = screen.getByRole('button');
    expect(button).toBeDisabled();
  });

  test('typing works in input field', () => {
    render(<App />);
    const input = screen.getByPlaceholderText(/ask about norwegian law/i);
    fireEvent.change(input, { target: { value: 'Hello' } });
    expect(input.value).toBe('Hello');
  });

});
