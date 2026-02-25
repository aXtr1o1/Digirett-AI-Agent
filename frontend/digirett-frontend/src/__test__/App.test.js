import { render, screen, fireEvent } from "@testing-library/react";
import ChatPage from "../pages/ChatPage";

// Mock ESM packages that break Jest
jest.mock("react-markdown", () => (props) => {
  return <div>{props.children}</div>;
});

jest.mock("remark-gfm", () => () => {});

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
    const button = screen.getAllByRole("button")[0]; // first button

    fireEvent.change(textarea, { target: { value: "Hi" } });

    expect(button).not.toBeDisabled();
  });

});
