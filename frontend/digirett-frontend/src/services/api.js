import axios from "axios";
import { API_BASE_URL } from "../utils/constants";

// Create axios instance
const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    "Content-Type": "application/json",
  },
});

// ─────────────────────────────────────────────────────────────
// Request interceptor
// Clerk auth is commented out — backend has no token validation yet.
// Uncomment the Clerk block when backend auth middleware is added.
// ─────────────────────────────────────────────────────────────
api.interceptors.request.use(
  async (config) => {
    try {
      // TODO: Uncomment when backend auth middleware is ready
      // const clerkToken = await window.Clerk?.session?.getToken();
      // if (clerkToken) {
      //   config.headers.Authorization = `Bearer ${clerkToken}`;
      // }
    } catch (error) {
      console.error("Error adding auth token:", error);
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// ─────────────────────────────────────────────────────────────
// Response interceptor — global error handling
// ─────────────────────────────────────────────────────────────
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response) {
      const { status, data } = error.response;

      if (status === 401) {
        // Unauthorized — redirect to sign in when auth is active
        // window.location.href = '/sign-in';
        console.error("Unauthorized:", data);
      } else if (status === 403) {
        console.error("Access forbidden:", data);
      } else if (status === 500) {
        console.error("Server error:", data);
      }
    } else if (error.request) {
      console.error("Network error:", error.message);
    } else {
      console.error("Error:", error.message);
    }

    return Promise.reject(error);
  }
);

export default api;