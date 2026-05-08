import React, { useEffect, useState } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import { SignUp, useUser } from "@clerk/clerk-react";
import { API_BASE_URL } from "../utils/constants";
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
        const response = await fetch(`${API_BASE_URL}/api/v1/invite/verify?token=${token}`);
        const data = await response.json();

        if (response.ok && data.valid) {
          setInvite(data);
        } else {
          setError(data.message || data.detail || "Failed to verify invitation.");
        }
      } catch (err) {
        setError("Network error. Please try again later.");
      } finally {
        setLoading(false);
      }
    };

    verifyToken();
  }, [token]);

  useEffect(() => {
    if (isLoaded && isSignedIn && invite) {
      // If user is already signed in and has a role, redirect to appropriate dashboard
      navigate(`/${invite.role}`);
    }
  }, [isLoaded, isSignedIn, invite, navigate]);

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
    <div className="min-h-screen flex flex-col items-center justify-center bg-gray-50 p-4 md:p-8">
      <div className="max-w-4xl w-full grid md:grid-cols-2 gap-8 items-center">
        {/* Welcome Text */}
        <div className="text-left">
          <div className="inline-flex items-center space-x-2 px-3 py-1 rounded-full bg-indigo-100 text-indigo-700 text-sm font-medium mb-6">
            <CheckCircle className="h-4 w-4" />
            <span>Invitation Verified</span>
          </div>
          <h1 className="text-4xl font-extrabold text-gray-900 leading-tight mb-4">
            Welcome to <span className="text-indigo-600">Digirett AI</span>
          </h1>
          <p className="text-lg text-gray-600 mb-8 leading-relaxed">
            You've been invited as a <span className="font-bold text-gray-900 underline decoration-indigo-300">{invite.role.toUpperCase()}</span>. 
            Sign up below to activate your account and access your dashboard.
          </p>
          
          <div className="space-y-4">
            <div className="flex items-start space-x-3">
              <div className="mt-1 flex-shrink-0 w-5 h-5 rounded-full bg-indigo-500 flex items-center justify-center text-white text-[10px] font-bold">1</div>
              <p className="text-gray-700 font-medium">Accept your professional role</p>
            </div>
            <div className="flex items-start space-x-3">
              <div className="mt-1 flex-shrink-0 w-5 h-5 rounded-full bg-indigo-500 flex items-center justify-center text-white text-[10px] font-bold">2</div>
              <p className="text-gray-700 font-medium">Complete your lawyer profile</p>
            </div>
            <div className="flex items-start space-x-3">
              <div className="mt-1 flex-shrink-0 w-5 h-5 rounded-full bg-indigo-500 flex items-center justify-center text-white text-[10px] font-bold">3</div>
              <p className="text-gray-700 font-medium">Start reviewing legal escalations</p>
            </div>
          </div>
        </div>

        {/* Clerk Signup */}
        <div className="bg-white p-2 rounded-3xl shadow-2xl overflow-hidden">
          <SignUp 
            routing="hash" 
            signInUrl="/sign-in" 
            redirectUrl={`/${invite.role}`}
            initialValues={{
              emailAddress: invite.masked_email || "",
            }}
          />
        </div>
      </div>
      
      <footer className="mt-12 text-gray-400 text-sm">
        &copy; 2026 Digirett AS. All rights reserved.
      </footer>
    </div>
  );
}
