// src/setupTests.js

import "@testing-library/jest-dom";
import axios from "axios";

/* ------------------------------------------------------------------ */
/* 1️⃣  Mock Axios (Prevents real HTTP calls in tests)               */
/* ------------------------------------------------------------------ */

jest.mock("axios");

// Make axios.create() return the mocked axios instance
axios.create = () => axios;

// Default mock responses
axios.get.mockResolvedValue({ data: [] });
axios.post.mockResolvedValue({ data: {} });
axios.put.mockResolvedValue({ data: {} });
axios.delete.mockResolvedValue({ data: {} });

/* ------------------------------------------------------------------ */
/* 2️⃣  Mock WebSocket (Prevents real WS connection)                  */
/* ------------------------------------------------------------------ */

class MockWebSocket {
  constructor(url) {
    this.url = url;
    this.readyState = 1; // OPEN

    // Simulate async open
    setTimeout(() => {
      if (this.onopen) this.onopen();
    }, 0);
  }

  send() {
    // You can simulate server messages here if needed
  }

  close() {
    this.readyState = 3; // CLOSED
    if (this.onclose) {
      this.onclose({ code: 1000, reason: "mock close" });
    }
  }
}

global.WebSocket = MockWebSocket;

/* ------------------------------------------------------------------ */
/* 3️⃣  Silence Expected Console Errors (Optional)                    */
/* ------------------------------------------------------------------ */

// Prevent noisy test logs from expected errors
beforeAll(() => {
  jest.spyOn(console, "error").mockImplementation(() => {});
});