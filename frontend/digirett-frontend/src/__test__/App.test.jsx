import React from "react";
import {
  afterEach,
  beforeEach,
  describe,
  expect,
  test,
  vi,
} from "vitest";

import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import ChatPage from "../pages/ChatPage";

// Mock Supabase
vi.mock("../lib/supabase", () => ({
  __esModule: true,

  supabase: {
    from: vi.fn(() => ({
      select: vi.fn().mockResolvedValue({
        data: [],
        error: null,
      }),

      insert: vi.fn().mockResolvedValue({
        data: [],
        error: null,
      }),

      update: vi.fn().mockResolvedValue({
        data: [],
        error: null,
      }),

      delete: vi.fn().mockResolvedValue({
        data: [],
        error: null,
      }),
    })),

    auth: {
      getSession: vi.fn().mockResolvedValue({
        data: {
          session: null,
        },
        error: null,
      }),

      onAuthStateChange: vi.fn(() => ({
        data: {
          subscription: {
            unsubscribe: vi.fn(),
          },
        },
      })),
    },
  },
}));

// Mock chat service
vi.mock("../services/chatService", () => ({
  __esModule: true,

  default: {
    sendMessage: vi.fn(
      (
        _conversationId,
        _message,
        _onChunk,
        onComplete,
        _onError
      ) => {
        if (onComplete) {
          onComplete({
            message: "Mocked response",
            sources: [],
            conversationId: "mock-conversation-id",
            messageId: "mock-message-id",
            metadata: {},
          });
        }

        return () => {};
      }
    ),
  },
}));

// Mock useChat hook
vi.mock("../hooks/useChat", () => ({
  __esModule: true,

  default: () => ({
    messages: [],
    input: "",
    setInput: vi.fn(),
    isLoading: false,
    error: null,
    sendMessage: vi.fn(),
    clearMessages: vi.fn(),
  }),
}));

// Mock Clerk
vi.mock("@clerk/clerk-react", () => ({
  useUser: () => ({
    user: {
      id: "test-user",
      fullName: "Test User",
      publicMetadata: {
        role: "user",
      },
      primaryEmailAddress: {
        emailAddress: "test@example.com",
      },
    },

    isLoaded: true,
    isSignedIn: true,
  }),

  useAuth: () => ({
    getToken: vi.fn().mockResolvedValue("mock-token"),
    userId: "test-user-id",
    isLoaded: true,
    isSignedIn: true,
  }),

  useClerk: () => ({
    signOut: vi.fn().mockResolvedValue(undefined),
  }),

  UserButton: () => <div data-testid="user-button" />,
  SignedIn: ({ children }) => <>{children}</>,
  SignedOut: () => null,
}));

// Mock ThemeProvider
vi.mock("../providers/ThemeProvider", () => ({
  __esModule: true,

  ThemeProvider: ({ children }) => <>{children}</>,

  useTheme: () => ({
    theme: "light",
    isDark: false,
    toggleTheme: vi.fn(),
  }),
}));

// Mock Markdown packages
vi.mock("react-markdown", () => ({
  __esModule: true,
  default: ({ children }) => <div>{children}</div>,
}));

vi.mock("remark-gfm", () => ({
  __esModule: true,
  default: () => undefined,
}));

const renderChatPage = () =>
  render(
    <MemoryRouter>
      <ChatPage />
    </MemoryRouter>
  );

let errorSpy;
let warningSpy;
let logSpy;

beforeEach(() => {
  errorSpy = vi
    .spyOn(console, "error")
    .mockImplementation(() => {});

  warningSpy = vi
    .spyOn(console, "warn")
    .mockImplementation(() => {});

  logSpy = vi
    .spyOn(console, "log")
    .mockImplementation(() => {});
});

afterEach(() => {
  errorSpy.mockRestore();
  warningSpy.mockRestore();
  logSpy.mockRestore();

  vi.clearAllMocks();
});

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