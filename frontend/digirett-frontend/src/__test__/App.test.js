import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import ChatPage from "../pages/ChatPage";

// ── Mock Supabase ─────────────────────────────────────────────────────────────
// supabase.js calls createClient() at module level using env vars that are
// undefined in CI, causing "supabaseUrl is required" before any test runs.
jest.mock("../lib/supabase", () => ({
  __esModule: true,
  supabase: {
    from: jest.fn(() => ({
      select: jest.fn().mockResolvedValue({ data: [], error: null }),
      insert: jest.fn().mockResolvedValue({ data: [], error: null }),
      update: jest.fn().mockResolvedValue({ data: [], error: null }),
      delete: jest.fn().mockResolvedValue({ data: [], error: null }),
    })),
    auth: {
      getSession: jest.fn().mockResolvedValue({ data: { session: null }, error: null }),
      onAuthStateChange: jest.fn(() => ({ data: { subscription: { unsubscribe: jest.fn() } } })),
    },
  },
}));

const renderChatPage = () =>
  render(
    <MemoryRouter>
      <ChatPage />
    </MemoryRouter>
  );

// ── Mock chatService FIRST ────────────────────────────────────────────────────
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
        return () => {};
      }
    ),
  },
}));

// ── Mock useChat hook ─────────────────────────────────────────────────────────
jest.mock("../hooks/useChat", () => () => ({
  messages:      [],
  input:         "",
  setInput:      jest.fn(),
  isLoading:     false,
  error:         null,
  sendMessage:   jest.fn(),
  clearMessages: jest.fn(),
}));

// ── Mock Clerk ───────────────────────────────────────────────────────────────
jest.mock("@clerk/clerk-react", () => ({
  useUser: () => ({
    user: {
      id: "test-user",
      fullName: "Test User",
      primaryEmailAddress: {
        emailAddress: "test@example.com",
      },
    },
    isLoaded: true,
    isSignedIn: true,
  }),
  useAuth: () => ({
    getToken: jest.fn(() => Promise.resolve("mock-token")),
    userId: "test-user-id",
  }),
  useClerk: () => ({
    signOut: jest.fn(() => Promise.resolve()),
  }),
}));

// ── Mock ThemeProvider ────────────────────────────────────────────────────────
jest.mock("../providers/ThemeProvider", () => ({
  __esModule: true,
  ThemeProvider: ({ children }) => <>{children}</>,
  useTheme: () => ({
    theme: "light",
    toggleTheme: jest.fn(),
  }),
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
    renderChatPage();
  });

  test("At least one button exists", () => {
    renderChatPage();
    const buttons = screen.getAllByRole("button");
    expect(buttons.length).toBeGreaterThan(0);
  });

});