import React, { useEffect, useState } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import { SignUp, useUser } from "@clerk/clerk-react";
import inviteService from "../services/inviteService";
import { CheckCircle, AlertCircle, Loader2 } from "lucide-react";

export default function InvitePage() {
  const [params] = useSearchParams();
  const token = params.get("token");
  const [invite, setInvite] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const { isSignedIn, isLoaded } = useUser();
  const navigate = useNavigate();

  useEffect(() => {
    if (!token) {
      setError("No invitation token found in the URL.");
      setLoading(false);
      return;
    }

    const verifyToken = async () => {
      try {
        const data = await inviteService.verifyToken(token);

        if (data.valid) {
          setInvite(data);
          // Store token in session storage so it persists across sign-in/sign-up
          sessionStorage.setItem("pending_invite_token", token);
        } else {
          setError(data.message || "Failed to verify invitation.");
        }
      } catch (err) {
        setError(err.message || "Network error. Please try again later.");
      } finally {
        setLoading(false);
      }
    };

    verifyToken();
  }, [token]);

  useEffect(() => {
    const claimAndRedirect = async () => {
      if (isLoaded && isSignedIn && invite) {
        try {
          // Claim the invite for the logged-in user
          await inviteService.acceptInvitation(token);
          // Go to provisioning to wait for metadata sync
          navigate(`/provisioning?target=${invite.role}`, { replace: true });
        } catch (err) {
          console.error("Failed to claim invitation:", err);
          setError("Could not link invitation to your account. Please contact an admin.");
        }
      }
    };

    claimAndRedirect();
  }, [isLoaded, isSignedIn, invite, navigate, token]);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="text-center">
          <Loader2 className="h-10 w-10 animate-spin text-indigo-600 mx-auto" />
          <p className="mt-4 text-gray-600 font-medium">Verifying invitation...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 p-4">
        <div className="max-w-md w-full bg-white rounded-2xl shadow-xl p-8 text-center">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-red-100 mb-6">
            <AlertCircle className="h-8 w-8 text-red-600" />
          </div>
          <h2 className="text-2xl font-bold text-gray-900 mb-2">Invalid Invitation</h2>
          <p className="text-gray-600 mb-8">{error}</p>
          <button
            onClick={() => navigate("/")}
            className="w-full py-3 px-4 bg-indigo-600 hover:bg-indigo-700 text-white font-semibold rounded-xl transition-colors shadow-lg shadow-indigo-200"
          >
            Go to Home
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 via-white to-indigo-50 flex items-center justify-center p-6">
      <div className="max-w-5xl w-full flex flex-col md:flex-row items-center justify-center gap-12 lg:gap-20">

        {/* Left Side: Branding & Info */}
        <div className="flex-1 max-w-lg">
          <div className="inline-flex items-center gap-2 px-4 py-2 rounded-2xl bg-indigo-50 border border-indigo-100 text-indigo-700 text-sm font-semibold mb-8 animate-fade-in">
            <CheckCircle className="h-4 w-4" />
            <span>Invitation Verified</span>
          </div>

          <h1 className="text-5xl font-black text-gray-900 leading-tight mb-6">
            Welcome to <br />
            <span className="text-transparent bg-clip-text bg-gradient-to-r from-indigo-600 to-blue-500">Digirett AI</span>
          </h1>

          <p className="text-xl text-gray-600 mb-10 leading-relaxed">
            You've been professionally invited as a <span className="font-extrabold text-gray-900 border-b-4 border-indigo-200">{invite.role.toUpperCase()}</span>.
            Join our platform to start managing legal escalations.
          </p>

          <div className="space-y-6">
            {[
              { num: 1, text: "Accept your professional role" },
              { num: 2, text: "Complete your expert profile" },
              { num: 3, text: "Access the case queue" }
            ].map((item) => (
              <div key={item.num} className="flex items-center gap-4 group">
                <div className="flex-shrink-0 w-8 h-8 rounded-xl bg-white shadow-sm border border-gray-100 flex items-center justify-center text-indigo-600 font-bold group-hover:scale-110 transition-transform">
                  {item.num}
                </div>
                <p className="text-gray-700 font-semibold">{item.text}</p>
              </div>
            ))}
          </div>

          <div className="mt-12 pt-8 border-t border-gray-100">
            <p className="text-sm text-gray-400">
              &copy; 2026 Digirett AS. Secured by professional-grade encryption.
            </p>
          </div>
        </div>

        {/* Right Side: Clerk Signup */}
        <div className="flex-shrink-0 w-full md:w-auto flex justify-center scale-95 origin-top">
          <SignUp
            routing="hash"
            signInUrl="/sign-in"
            redirectUrl={`/provisioning?target=${invite.role}&token=${token}`}
            appearance={{
              variables: {
                colorPrimary: "#4f46e5",
                colorText: "#1f2937",
                colorBackground: "#ffffff",
                colorInputBackground: "#f9fafb",
                colorInputText: "#1f2937",
                borderRadius: "1.25rem",
                spacingUnit: "0.75rem", // Reduce overall spacing
              },
              elements: {
                card: "shadow-[0_15px_40px_rgba(0,0,0,0.08)] border border-gray-100 max-w-[400px]",
                headerTitle: "text-xl font-black text-gray-900",
                headerSubtitle: "text-sm text-gray-500",
                socialButtonsBlockButton: "border-gray-200 hover:bg-gray-50 h-10",
                formButtonPrimary: "bg-indigo-600 hover:bg-indigo-700 text-sm py-2.5 h-11",
                footerActionLink: "text-indigo-600 hover:text-indigo-700 font-semibold text-sm",
                formFieldLabel: "text-xs font-bold text-gray-600 mb-1",
                formFieldInput: "h-10 text-sm",
                rootBox: "mx-auto",
              }
            }}
            initialValues={{
              emailAddress: invite.masked_email || "",
            }}
          />
        </div>
      </div>
    </div>
  );
}
