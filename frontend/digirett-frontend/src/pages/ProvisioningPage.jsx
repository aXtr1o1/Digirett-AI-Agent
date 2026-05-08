import React, { useEffect, useState } from "react";
import { useUser } from "@clerk/clerk-react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Loader2, CheckCircle } from "lucide-react";
import inviteService from "../services/inviteService";

export default function ProvisioningPage() {
  const { user, isLoaded } = useUser();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const target = params.get("target");
  const token = params.get("token");
  const [dots, setDots] = useState("");
  const [status, setStatus] = useState("Initializing setup...");

  useEffect(() => {
    const interval = setInterval(() => {
      setDots(prev => prev.length >= 3 ? "" : prev + ".");
    }, 500);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (!isLoaded || !user) return;

    // Clear session storage once we start provisioning
    sessionStorage.removeItem("pending_invite_token");

    let attempts = 0;
    const maxAttempts = 15; // 15 seconds total

    const runSetup = async () => {
      let finalTarget = target;

      // 1. If we have a token, claim it first
      if (token) {
        try {
          setStatus("Claiming your professional role...");
          const res = await inviteService.acceptInvitation(token);
          finalTarget = res.role;
        } catch (err) {
          console.error("Failed to claim invitation in provisioning:", err);
          // Fallback: maybe it was already claimed, continue to sync check
        }
      }

      // 2. Poll for role sync in Clerk metadata
      const checkRole = async () => {
        setStatus("Syncing professional permissions...");
        await user.reload();
        
        const role = user.publicMetadata?.role;
        
        if (role && (role === finalTarget || (finalTarget === 'lawyer' && role === 'admin'))) {
          const redirectPath = role === 'lawyer' ? '/lawyer' : `/${role}`;
          navigate(redirectPath, { replace: true });
        } else if (attempts < maxAttempts) {
          attempts++;
          setTimeout(checkRole, 1000);
        } else {
          // Fallback to home redirect logic
          navigate("/", { replace: true });
        }
      };

      checkRole();
    };

    runSetup();
  }, [isLoaded, user, target, token, navigate]);

  return (
    <div className="min-h-screen bg-white flex flex-col items-center justify-center p-4">
      <div className="max-w-md w-full text-center">
        <div className="relative mb-8 flex justify-center">
          <div className="absolute inset-0 bg-indigo-100 rounded-full animate-ping opacity-25 scale-150"></div>
          <div className="relative bg-white p-4 rounded-full shadow-lg border border-indigo-50">
            <Loader2 className="h-12 w-12 text-indigo-600 animate-spin" />
          </div>
        </div>
        
        <h1 className="text-3xl font-black text-gray-900 mb-4">
          Setting up your workspace{dots}
        </h1>
        <p className="text-gray-600 mb-8 leading-relaxed font-medium">
          {status}
        </p>
        
        <div className="space-y-3">
          <div className="flex items-center justify-center space-x-2 text-sm font-medium text-gray-400">
            <CheckCircle className="h-4 w-4 text-green-500" />
            <span>Account created successfully</span>
          </div>
          <div className="flex items-center justify-center space-x-2 text-sm font-medium text-indigo-600 animate-pulse">
            <div className="h-1.5 w-1.5 bg-indigo-600 rounded-full"></div>
            <span>Syncing professional role</span>
          </div>
        </div>
      </div>
    </div>
  );
}
