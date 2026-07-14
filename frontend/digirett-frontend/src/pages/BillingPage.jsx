import React, { useEffect } from "react";
import { useUser } from "@clerk/clerk-react";
import { useNavigate } from "react-router-dom";
import { Loader2, X } from "lucide-react";
import BackgroundLayer from "../components/common/BackgroundLayer";
import { useTheme } from "../providers/ThemeProvider";

export default function BillingPage() {
  const { user, isLoaded: userLoaded } = useUser();
  const navigate = useNavigate();
  const { theme, isDark } = useTheme();

  // Read environment keys for real Stripe Embedding
  const stripePublishableKey = process.env.REACT_APP_STRIPE_PUBLISHABLE_KEY;
  const stripePricingTableId = process.env.REACT_APP_STRIPE_PRICING_TABLE_ID;
  const hasStripeConfig = !!(stripePublishableKey && stripePricingTableId);
  // Log warning if Stripe configuration is missing
useEffect(() => {
  if (process.env.NODE_ENV !== "production") {
    if (!stripePublishableKey) {
      console.warn(
        "Missing environment variable: REACT_APP_STRIPE_PUBLISHABLE_KEY"
      );
    }

    if (!stripePricingTableId) {
      console.warn(
        "Missing environment variable: REACT_APP_STRIPE_PRICING_TABLE_ID"
      );
    }

    if (!hasStripeConfig) {
      console.warn(
        "Stripe Pricing Table is disabled because the required environment variables are missing."
      );
    }
  }
}, [stripePublishableKey, stripePricingTableId, hasStripeConfig]);

  useEffect(() => {
    if (userLoaded && user) {
      const role = user.publicMetadata?.role || "user";
      if (role === "lawyer" || role === "admin" || role === "system_admin") {
        navigate("/chat");
        return;
      }
    }
  }, [user, userLoaded, navigate]);

  // Load Stripe Pricing Table script
  useEffect(() => {
    if (hasStripeConfig) {
      const script = document.createElement("script");
      script.src = "https://js.stripe.com/v3/pricing-table.js";
      script.async = true;
      document.body.appendChild(script);
    }
  }, [hasStripeConfig]);

  const getStripeElementHtml = () => {
    return {
      __html: `<stripe-pricing-table 
        pricing-table-id="${stripePricingTableId}" 
        publishable-key="${stripePublishableKey}"
        client-reference-id="${user?.id || ""}"
        customer-email="${user?.primaryEmailAddress?.emailAddress || ""}"
      ></stripe-pricing-table>`
    };
  };

  if (!userLoaded) {
    return (
      <div className="flex h-screen items-center justify-center bg-black text-white">
        <div className="flex flex-col items-center gap-3">
          <Loader2 className="h-10 w-10 animate-spin text-indigo-500" />
          <p className="text-gray-400 font-medium">Loading billing center...</p>
        </div>
      </div>
    );
  }

  return (
    <div className={`relative min-h-screen w-full flex flex-col justify-between overflow-x-hidden ${isDark ? "text-white" : "text-gray-900"
      }`}>
      <BackgroundLayer theme={theme} />

      {/* Floating Close Button in Top Right */}
      <button
        onClick={() => navigate("/chat")}
        className={`absolute top-6 right-6 p-2.5 rounded-full border transition-all duration-200 z-50 shadow-md ${isDark
          ? "bg-[#161622]/80 border-white/10 text-gray-400 hover:text-white hover:bg-slate-850/80"
          : "bg-white/90 border-gray-200 text-gray-500 hover:text-gray-900 hover:bg-gray-100/90"
          }`}
        style={{ backdropFilter: "blur(8px)" }}
        title="Close and return to chat"
      >
        <X size={18} />
      </button>

      {/* Main Content Area */}
      <div className="flex-1 max-w-[1400px] w-full mx-auto px-6 py-6 md:py-10 flex flex-col items-center z-10">
        {/* Top Header */}
        <div className="font-serif text-center mb-6 md:mb-8">
          <h1 className={`text-2xl md:text-3.5xl font-bold tracking-tight mb-2 ${isDark ? "text-white" : "text-gray-950"}`}>
            Upgrade your plan
          </h1>
          <p className={`text-xs md:text-sm max-w-lg mx-auto opacity-80 ${isDark ? "text-gray-400" : "text-gray-500"}`}>
            Choose the billing tier that fits your legal consulting workload. All payments run securely via Stripe.
          </p>
        </div>

        {/* Pricing Cards Grid */}
        <div className="w-full">
          {hasStripeConfig ? (
            <div className="w-full">
              <div
                className="w-full"
                dangerouslySetInnerHTML={getStripeElementHtml()}
              />
            </div>
          ) : (
            <div className="text-center py-12 text-gray-500">
              Stripe connection is not configured. Please contact the administrator.
            </div>
          )}
        </div>
      </div>

      {/* Footer Area */}
      <div className={`w-full text-center py-6 text-[10px] font-medium tracking-wide ${isDark ? "text-gray-600" : "text-gray-400"}`}>
        DigiRett © 2026. Billed securely via Stripe.
      </div>
    </div>
  );
}
