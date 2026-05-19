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
      const status = error.response.status;
      const data = error.response.data;
      let detail = data?.detail || data?.message || "";

      // Handle cases where detail might be an array (validation errors)
      if (Array.isArray(detail) && detail.length > 0) {
        detail = detail[0]?.msg || JSON.stringify(detail);
      } else if (typeof detail === "object" && detail !== null) {
        detail = detail.message || detail.error || JSON.stringify(detail);
      }

      const detailStr = String(detail).toLowerCase();

      if (status === 401) {
        const isExpired = detailStr.includes("expired") || detailStr.includes("jwt") || detailStr.includes("signature");
        message = isExpired ? "Session expired. Please sign in again to continue." : "Authentication required. Please sign in.";
        if (isExpired && window.Clerk) {
          window.Clerk.signOut();
        }
      } else if (status === 403) {
        message = "Access denied. You do not have permission for this action.";
      } else if (status === 429) {
        message = detail || "Too many requests. Please try again later.";
      } else {
        // Fallback to detail if available, otherwise status-based generic message
        message = detail || (status === 500 ? "Server error. Please try again." : "Something went wrong");
      }
    } else if (error.request) {
      message = "Network error. Please check your connection.";
    }

    // Create error object and attach response data for deeper inspection if needed
    const finalError = new Error(String(message));
    finalError.status = error.response?.status;
    finalError.data = error.response?.data;

    return Promise.reject(finalError);
  }
);

export default api;