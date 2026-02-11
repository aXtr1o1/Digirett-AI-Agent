// jest-dom adds custom jest matchers for asserting on DOM nodes.
// allows you to do things like:
// expect(element).toHaveTextContent(/react/i)
// learn more: https://github.com/testing-library/jest-dom
import '@testing-library/jest-dom';
// Mock scrollIntoView for JSDOM
// mock env values for tests
process.env.REACT_APP_API_BASE_URL = 'http://mock-api.test';
window.HTMLElement.prototype.scrollIntoView = jest.fn();
// jest-dom adds custom jest matchers for asserting on DOM nodes.
// allows you to do things like:
// expect(element).toHaveTextContent(/react/i)
// learn more: https://github.com/testing-library/jest-dom
import '@testing-library/jest-dom';

// Fix TextEncoder/TextDecoder for JSDOM (Windows/CRA)
import { TextEncoder, TextDecoder } from 'util';

global.TextEncoder = TextEncoder;
global.TextDecoder = TextDecoder;

// Mock ESM-only modules used by App.js
jest.mock('remark-gfm', () => ({
  __esModule: true,
  default: () => null,
}));

jest.mock('react-markdown', () => ({
  __esModule: true,
  default: ({ children }) => <div>{children}</div>,
}));
