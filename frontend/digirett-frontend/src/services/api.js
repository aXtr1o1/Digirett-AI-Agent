import axios from "axios";
import { API_BASE_URL } from "../utils/constants";

const api = axios.create({
  baseURL: `${API_BASE_URL}/api/v1`,
  headers: {
    "Content-Type": "application/json",
  },
});

// Request interceptor
api.interceptors.request.use(
  async (config) => {
    try {
      const clerkToken = await window.Clerk?.session?.getToken();
      if (clerkToken) {
        config.headers.Authorization = `Bearer ${clerkToken}`;
      }
    } catch (error) {
      console.error("Error adding auth token:", error);
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Response interceptor
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response) {
      const { status, data } = error.response;

      if (status === 401) {
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

    let message = "Something went wrong";

    if (error.response) {
      if (error.response.status === 500) {
        message = "Server error. Please try again.";
      } else if (error.response.status === 404) {
        message = "Data not found.";
      } else if (error.response.status === 401) {
        const detail = error.response.data?.detail || "";
        const isExpired = typeof detail === 'string' && detail.toLowerCase().includes("expired");
        message = isExpired ? "Session expired. Please log in again." : "Please login again.";
      } else {
        message = error.response.data?.detail || "Something went wrong";
      }
    } else if (error.request) {
      message = "Server not reachable";
    }

    return Promise.reject(new Error(message));
  }
);

export default api;