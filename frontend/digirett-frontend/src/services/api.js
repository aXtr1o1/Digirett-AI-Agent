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
      // Enable when backend auth is ready
      // const clerkToken = await window.Clerk?.session?.getToken();
      // if (clerkToken) {
      //   config.headers.Authorization = `Bearer ${clerkToken}`;
      // }
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
    let message = "Something went wrong";

    if (error.response) {
      message =
        error.response.data?.message ||   // ✅ backend global handler
        error.response.data?.detail ||    // fallback
        "Something went wrong";
    } 
    else if (error.request) {
      message = "Server not reachable";
    }

    // 🔥 POPUP HERE
    alert(message);

    // ❗ IMPORTANT: return original error (not new Error)
    return Promise.reject(error);
  }
);

export default api;