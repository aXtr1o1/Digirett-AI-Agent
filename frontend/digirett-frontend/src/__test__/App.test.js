import { render, screen, fireEvent } from "@testing-library/react";
import ChatPage from "../pages/ChatPage";

// ── Mock chatService FIRST ────────────────────────────────────────────────────
// chatService.js line 28 does:
//   const cleanBase = API_BASE_URL.replace(/\/+$/, "")
// API_BASE_URL comes from ../utils/constants which reads process.env.REACT_APP_API_URL.
// That env var is undefined in CI, so .replace() throws before any test runs.
// Mocking the whole module prevents chatService.js from ever being executed.
//
// chatService uses a DEFAULT export (export default chatService) so the mock
// must use __esModule: true + default: { ... }
jest.mock("../services/chatService", () => ({
  __esModule: true,
  default: {
    sendMessage: jest.fn(
      (_conversationId, _message, _onChunk, onComplete, _onError) => {
        if (onComplete) {
          onComplete({
            message:        "Mocked response",
            sources:        [],
            conversationId: "mock-conversation-id",
            messageId:      "mock-message-id",
            metadata:       {},
          });
        }
        // Return cancel function — same API as the real sendMessage
        return () => {};
      }
    ),
  },
}));

// ── Mock useChat hook ─────────────────────────────────────────────────────────
// useChat wraps chatService internally — stub it so ChatPage gets clean state
// without needing any real service or WebSocket connection.
jest.mock("../hooks/useChat", () => () => ({
  messages:      [],
  input:         "",
  setInput:      jest.fn(),
  isLoading:     false,
  error:         null,
  sendMessage:   jest.fn(),
  clearMessages: jest.fn(),
}));

// ── Mock ESM packages that break Jest's CommonJS transform ───────────────────
jest.mock("react-markdown", () => (props) => <div>{props.children}</div>);
jest.mock("remark-gfm", () => () => {});

// ── Suppress console noise during tests ──────────────────────────────────────
beforeEach(() => {
  jest.spyOn(console, "error").mockImplementation(() => {});
  jest.spyOn(console, "warn").mockImplementation(() => {});
  jest.spyOn(console, "log").mockImplementation(() => {});
});

afterEach(() => {
  console.error.mockRestore();
  console.warn.mockRestore();
  console.log.mockRestore();
  jest.clearAllMocks();
});

// =============================================================================

describe("Chat Page Tests", () => {

  test("Chat page renders without crashing", () => {
    render(<ChatPage />);
  });

  test("Textarea is present", () => {
    render(<ChatPage />);
    const textarea = screen.getByPlaceholderText(/Ask Anything.../i);
    expect(textarea).toBeInTheDocument();
  });

  test("Typing in textarea works", () => {
    render(<ChatPage />);
    const textarea = screen.getByPlaceholderText(/Ask Anything.../i);

    fireEvent.change(textarea, { target: { value: "Hello" } });

    expect(textarea.value).toBe("Hello");
  });

  test("At least one button exists", () => {
    render(<ChatPage />);
    const buttons = screen.getAllByRole("button");
    expect(buttons.length).toBeGreaterThan(0);
  });

  test("Send button enables after typing", () => {
    render(<ChatPage />);
    const textarea = screen.getByPlaceholderText(/Ask Anything.../i);
    const button = screen.getAllByRole("button")[0];

    fireEvent.change(textarea, { target: { value: "Hi" } });

    expect(button).not.toBeDisabled();
  });

});