import React, { useState } from "react";
import { useSignIn } from "@clerk/clerk-react";
import { Link, useNavigate } from "react-router-dom";
import SocialLogin from "../components/auth/SocialLogin";
import hitlService from "../services/hitlService";

const SignInPage = () => {
  const { signIn, isLoaded, setActive } = useSignIn();
  const navigate = useNavigate();
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!isLoaded) return;

    setIsLoading(true);
    setError("");

    try {
      // Suspension check
      try {
        const statusCheck = await hitlService.checkStatus(identifier);
        if (statusCheck && statusCheck.is_suspended) {
          setError("This account has been restricted.");
          setIsLoading(false);
          return;
        }
      } catch (checkErr) {
        console.warn("Suspension check failed:", checkErr);
      }

      const result = await signIn.create({
        identifier,
        password,
      });

      if (result.status === "complete") {
        await setActive({ session: result.createdSessionId });
        navigate("/");
      } else {
        setError("Sign in incomplete. Please try again.");
      }
    } catch (err) {
      console.error("Sign in error:", err);
      // Look for specific session errors
      const errorStr = JSON.stringify(err).toLowerCase();
      if (errorStr.includes("session_already_exists") || err.errors?.some(e => e.code === 'session_already_exists')) {
        navigate("/");
        return;
      }
      setError(err.errors?.[0]?.longMessage || err.errors?.[0]?.message || "Invalid username or password");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-black flex items-center justify-center p-4 py-4">
      <div className="w-full max-w-[480px]">
        {/* Unified Card Container */}
        <div className="bg-[#0f0f0f] border border-gray-800 rounded-[32px] p-6 sm:px-10 sm:pt-6 sm:pb-3 shadow-2xl space-y-3 overflow-hidden">
          <div className="space-y-0.5 text-center">
            <h1 className="text-xl font-bold text-white tracking-tight">Welcome back</h1>
            <p className="text-gray-500 text-[9px]">Please enter your details to sign in</p>
          </div>

          <SocialLogin />

          <div className="relative mt-5 mb-5">
            <div className="absolute inset-0 flex items-center">
              <span className="w-full border-t border-gray-800/50"></span>
            </div>
            <div className="relative flex justify-center text-[8px] uppercase tracking-[0.2em]">
              <span className="bg-[#0f0f0f] px-3 text-gray-500 font-bold">Or continue with</span>
            </div>
          </div>

          <div className="w-full mt-2">
            <form onSubmit={handleSubmit} className="w-full space-y-3">
              {error && (
                <div className="text-red-400 text-[11px] text-center bg-red-500/10 rounded-xl p-2.5 border border-red-500/20 font-medium">
                  {error}
                </div>
              )}
              
              <div className="flex flex-col">
                <label className="text-gray-400 font-medium text-[10px] mb-1">Email address or username</label>
                <input
                  type="text"
                  value={identifier}
                  onChange={(e) => setIdentifier(e.target.value)}
                  placeholder="Enter email or username"
                  className="bg-[#1a1a1a] border border-gray-800 text-white focus:border-white rounded-xl h-9 transition-all px-4 w-full text-sm outline-none placeholder-gray-600"
                  required
                />
              </div>

              <div className="flex flex-col">
                <label className="text-gray-400 font-medium text-[10px] mb-1">Password</label>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  className="bg-[#1a1a1a] border border-gray-800 text-white focus:border-white rounded-xl h-9 transition-all px-4 w-full text-sm outline-none placeholder-gray-600"
                  required
                />
              </div>

              <div className="pt-2">
                <button
                  type="submit"
                  disabled={isLoading}
                  className="bg-white text-black hover:bg-gray-100 font-bold py-2.5 w-full rounded-xl transition-all active:scale-[0.98] flex items-center justify-center text-sm disabled:opacity-70 disabled:cursor-not-allowed"
                >
                  {isLoading ? "Signing in..." : "Continue"}
                </button>
              </div>

              <div className="flex items-center justify-center pt-3 pb-1">
                <span className="text-gray-500 text-[11px] mr-1">Don't have an account?</span>
                <Link to="/sign-up" className="text-white font-bold text-[11px] hover:text-gray-300 transition-colors">
                  Sign up
                </Link>
              </div>
            </form>
          </div>
        </div>
      </div>
    </div>
  );
};

export default SignInPage;
