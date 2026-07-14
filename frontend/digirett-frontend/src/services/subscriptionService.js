import api from "./api";

// Service to manage client-side mockup subscriptions in Stripe Sandbox
const subscriptionService = {
  /**
   * Retrieves the user's active plan from localStorage, isolative by Clerk User ID.
   * Defaults to "free".
   */
  getSubscription(userId) {
    if (!userId) return "free";
    return localStorage.getItem(`digirett_sub_${userId}`) || "free";
  },

  /**
   * Updates the user's active plan in localStorage and dispatches a global window event
   * to notify listening components to update immediately without a full page refresh.
   */
  setSubscription(userId, planId) {
    if (!userId) return;
    localStorage.setItem(`digirett_sub_${userId}`, planId);
    window.dispatchEvent(new CustomEvent("subscription_change", { detail: { planId } }));
  },

  /**
   * Reverts the user's plan to "free" and dispatches the update event.
   */
  async cancelSubscription(userId) {
    // Fetch customer billing portal session URL from backend
    const response = await api.post("/billing/portal-session");
    if (response.data?.url) {
      window.location.href = response.data.url;
    } else {
      throw new Error("Failed to retrieve billing portal link.");
    }
  }
};

export default subscriptionService;
