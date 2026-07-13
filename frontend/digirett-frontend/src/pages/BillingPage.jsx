import React, { useEffect, useState } from "react";
import { useUser } from "@clerk/clerk-react";
import { useNavigate } from "react-router-dom";
import { ArrowLeft, Loader2, X, Check, Sparkles } from "lucide-react";
import subscriptionService from "../services/subscriptionService";
import BackgroundLayer from "../components/common/BackgroundLayer";
import { useTheme } from "../providers/ThemeProvider";

// Clean, ChatGPT-styled plans with icons mapped to real policy features
const PLANS = [
  {
    id: "startup",
    name: "Start-up",
    monthlyPrice: "490",
    annualPrice: "4,900",
    description: "Ideal for individual founders and early stage teams.",
    features: [
      "1 user seat",
      "Unlimited AI legal & QA",
      "All 12 legal domains covered",
      "1 included lawyer hour/month",
      "Lovdata source citations"
    ]
  },
  {
    id: "vekst",
    name: "Vekst",
    monthlyPrice: "1,490",
    annualPrice: "14,900",
    description: "Perfect for growing businesses with expanding legal needs.",
    features: [
      "Up to 3 user seats",
      "Unlimited AI legal & QA",
      "All 12 legal domains covered",
      "3 included lawyer hours/month",
      "Lovdata source citations"
    ],
    popular: true
  },
  {
    id: "smb",
    name: "SMB",
    monthlyPrice: "2,990",
    annualPrice: "29,900",
    description: "Built for small to medium enterprises requiring regular counsel.",
    features: [
      "Up to 10 user seats",
      "Unlimited AI legal & QA",
      "All 12 legal domains covered",
      "8 included lawyer hours/month",
      "Lovdata source citations"
    ]
  },
  {
    id: "enterprise",
    name: "Enterprise",
    monthlyPrice: "7,990",
    annualPrice: "79,900",
    description: "Tailored for organizations needing full support.",
    features: [
      "Unlimited user seats",
      "Unlimited AI legal & QA",
      "All 12 legal domains covered",
      "20 included lawyer hours/month",
      "Lovdata source citations"
    ]
  }
];

export default function BillingPage() {
  const { user, isLoaded: userLoaded } = useUser();
  const navigate = useNavigate();
  const { theme, isDark } = useTheme();

  const [activePlan, setActivePlan] = useState("free");
  const [billingPeriod, setBillingPeriod] = useState("monthly"); // "monthly" or "annual"
  const [loading, setLoading] = useState(false);
  const [selectedPlanId, setSelectedPlanId] = useState(null);

  // Read environment keys for real Stripe Embedding
  const stripePublishableKey = process.env.REACT_APP_STRIPE_PUBLISHABLE_KEY;
  const stripePricingTableId = process.env.REACT_APP_STRIPE_PRICING_TABLE_ID;
  const hasStripeConfig = !!(stripePublishableKey && stripePricingTableId);

  useEffect(() => {
    if (userLoaded && user) {
      const role = user.publicMetadata?.role || "user";
      if (role === "lawyer" || role === "admin" || role === "system_admin") {
        navigate("/chat");
        return;
      }
      const plan = subscriptionService.getSubscription(user.id);
      setActivePlan(plan);
    }
  }, [user, userLoaded, navigate]);

  // Listen to subscription state change events
  useEffect(() => {
    const handleSubChange = () => {
      if (user) {
        const plan = subscriptionService.getSubscription(user.id);
        setActivePlan(plan);
      }
    };
    window.addEventListener("subscription_change", handleSubChange);
    return () => window.removeEventListener("subscription_change", handleSubChange);
  }, [user]);

  // Load Stripe Pricing Table script
  useEffect(() => {
    if (hasStripeConfig) {
      const script = document.createElement("script");
      script.src = "https://js.stripe.com/v3/pricing-table.js";
      script.async = true;
      document.body.appendChild(script);
    }
  }, [hasStripeConfig]);

  // Mock checkout processor
  const handleUpgradeMock = (planId) => {
    setLoading(true);
    setSelectedPlanId(planId);
    setTimeout(() => {
      setLoading(false);
      setSelectedPlanId(null);
      // Redirect to chat with mock session_id parameter
      navigate(`/chat?session_id=mock_session_table_${planId}_${billingPeriod}_${Date.now()}`);
    }, 1200);
  };

  const handleCancelSub = () => {
    if (window.confirm("Are you sure you want to cancel your premium subscription and revert to the Free tier?")) {
      subscriptionService.cancelSubscription(user.id);
      alert("Subscription cancelled successfully.");
    }
  };

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
        <div className="text-center mb-6 md:mb-8">
          <h1 className={`text-2xl md:text-3.5xl font-bold tracking-tight mb-2 ${isDark ? "text-white" : "text-gray-950"}`}>
            Upgrade your plan
          </h1>
          <p className={`text-xs md:text-sm max-w-lg mx-auto opacity-80 ${isDark ? "text-gray-400" : "text-gray-500"}`}>
            Choose the billing tier that fits your legal consulting workload. All payments run in Stripe Sandbox.
          </p>
        </div>

        {/* Custom Toggle Switch for fallback pricing */}
        {!hasStripeConfig && (
          <div className="flex items-center justify-center gap-3.5 mb-10">
            <span className={`text-xs md:text-sm font-semibold transition-colors ${billingPeriod === "monthly" ? (isDark ? "text-white" : "text-gray-950") : "text-gray-500"}`}>
              Billed monthly
            </span>
            <button
              onClick={() => setBillingPeriod(billingPeriod === "monthly" ? "annual" : "monthly")}
              className={`relative inline-flex h-6 w-11 items-center rounded-full transition-all duration-300 focus:outline-none ${billingPeriod === "annual" ? "bg-indigo-600" : "bg-gray-600"
                }`}
            >
              <span
                className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform duration-300 ${billingPeriod === "annual" ? "translate-x-6" : "translate-x-1"
                  }`}
              />
            </button>
            <span className={`text-xs md:text-sm font-semibold transition-colors ${billingPeriod === "annual" ? (isDark ? "text-white" : "text-gray-950") : "text-gray-500"}`}>
              Billed annually (Save 15%)
            </span>
          </div>
        )}

        {/* Active subscription banner / Cancel option */}
        {activePlan !== "free" && (
          <div className={`max-w-xl mx-auto w-full mb-10 p-4 rounded-xl border text-center flex flex-col md:flex-row items-center justify-between gap-4 ${isDark
            ? "bg-indigo-950/20 border-indigo-500/20 text-indigo-300"
            : "bg-indigo-50/50 border-indigo-200 text-indigo-800"
            }`}>
            <span className="text-xs font-semibold">
              You are currently subscribed to the <strong className="uppercase">{activePlan}</strong> tier.
            </span>
            <button
              onClick={handleCancelSub}
              className="px-3.5 py-1.5 bg-red-500/15 hover:bg-red-500 text-red-400 hover:text-white border border-red-500/20 rounded-lg text-xs font-bold transition-all shrink-0"
            >
              Cancel Active Subscription
            </button>
          </div>
        )}

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
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
              {PLANS.map((plan) => {
                const isCurrent = activePlan === plan.id;
                const price = billingPeriod === "monthly" ? plan.monthlyPrice : plan.annualPrice;
                return (
                  <div
                    key={plan.id}
                    className={`relative rounded-2xl border p-6 flex flex-col transition-all duration-300 ${plan.popular
                      ? isDark
                        ? "bg-[#181829]/95 border-indigo-500/40 shadow-indigo-500/10 shadow-xl"
                        : "bg-indigo-50/40 border-indigo-200 shadow-indigo-500/5 shadow-xl"
                      : isDark
                        ? "bg-[#11111b]/80 border-white/5 hover:border-white/10"
                        : "bg-white/90 border-gray-200 hover:border-gray-300 shadow-sm"
                      }`}
                  >
                    {plan.popular && (
                      <span className="absolute -top-3 left-1/2 -translate-x-1/2 px-3 py-0.5 text-[9px] uppercase font-black tracking-widest text-white bg-gradient-to-r from-indigo-500 to-purple-600 rounded-full shadow-md">
                        Popular Choice
                      </span>
                    )}

                    {/* Header */}
                    <h3 className={`text-xl font-bold ${isDark ? "text-white" : "text-gray-950"}`}>
                      {plan.name}
                    </h3>

                    {/* Pricing */}
                    <div className="flex items-baseline gap-1 mt-2 mb-1">
                      <span className={`text-3xl font-black ${isDark ? "text-white" : "text-gray-950"}`}>
                        kr {price}
                      </span>
                      <span className={`text-[10px] font-bold uppercase ${isDark ? "text-gray-500" : "text-gray-450"}`}>
                        / {billingPeriod === "monthly" ? "mo" : "yr"}
                      </span>
                    </div>

                    {/* Description */}
                    <p className={`text-xs mt-1 mb-4 leading-relaxed min-h-[36px] ${isDark ? "text-gray-400" : "text-gray-500"}`}>
                      {plan.description}
                    </p>

                    {/* Action Button */}
                    <button
                      disabled={loading || isCurrent}
                      onClick={() => handleUpgradeMock(plan.id)}
                      className={`w-full py-2.5 rounded-xl text-xs font-bold transition-all duration-200 flex items-center justify-center gap-2 mb-6 ${isCurrent
                        ? isDark
                          ? "bg-white/5 border border-white/10 text-white/30 cursor-default"
                          : "bg-gray-100 border border-gray-200 text-gray-400 cursor-default"
                        : plan.popular
                          ? "bg-gradient-to-r from-indigo-500 to-purple-600 hover:from-indigo-600 hover:to-purple-700 text-white shadow-lg shadow-indigo-500/20 active:scale-[0.99]"
                          : isDark
                            ? "bg-white text-gray-950 hover:bg-gray-100 active:scale-[0.99]"
                            : "bg-gray-950 text-white hover:bg-gray-900 active:scale-[0.99]"
                        }`}
                    >
                      {loading && selectedPlanId === plan.id ? (
                        <>
                          <Loader2 size={12} className="animate-spin" />
                          Processing...
                        </>
                      ) : isCurrent ? (
                        "Current Plan"
                      ) : (
                        `Upgrade to ${plan.name}`
                      )}
                    </button>

                    {/* Features list */}
                    <ul className="flex flex-col gap-3.5">
                      {plan.features.map((feat, index) => (
                        <li key={index} className="flex items-start gap-2.5 text-xs">
                          <Check className={`h-4 w-4 shrink-0 mt-0.5 ${isDark ? "text-indigo-400" : "text-indigo-600"}`} />
                          <span className={isDark ? "text-gray-300" : "text-gray-700"}>{feat}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {/* Footer Area */}
      <div className={`w-full text-center py-6 text-[10px] font-medium tracking-wide ${isDark ? "text-gray-600" : "text-gray-400"}`}>
        DigiRett © 2026. Billed securely via Stripe. All mock checkouts run in Sandbox Mode.
      </div>
    </div>
  );
}
