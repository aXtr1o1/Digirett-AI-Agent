import React, { useState } from "react";
import { useSignIn, useClerk } from "@clerk/clerk-react";
import { Link, useNavigate } from "react-router-dom";
import { Eye, EyeOff } from "lucide-react";
import SocialLogin from "../components/auth/SocialLogin";
import hitlService from "../services/hitlService";

const SignInPage = () => {
  const { signIn, isLoaded, setActive } = useSignIn();
  const { signOut } = useClerk();
  const navigate = useNavigate();
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [successMsg, setSuccessMsg] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  
  // UI State
  const [showPassword, setShowPassword] = useState(false);
  const [showNewPassword, setShowNewPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  
  // Forgot Password State
  const [resetStep, setResetStep] = useState("signin"); // "signin" | "forgot_password" | "verify_reset"
  const [resetCode, setResetCode] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");

  const handleResetRequest = async (e) => {
    e?.preventDefault();
    if (!identifier) {
      setError("Please enter your email address or username.");
      return;
    }
    
    setIsLoading(true);
    setError("");
    setSuccessMsg("");
    
    try {
      let resetIdentifier = identifier;
      try {
        const statusCheck = await hitlService.checkStatus(identifier);
        if (statusCheck && statusCheck.user_name) {
          resetIdentifier = statusCheck.user_name;
        }
      } catch (checkErr) {
        console.warn("Reset status check failed:", checkErr);
      }

      const si = await signIn.create({ identifier: resetIdentifier });
      
      const emailFactor = si.supportedFirstFactors?.find(
        (factor) => factor.strategy === "reset_password_email_code"
      );

      if (!emailFactor) {
        setError("Password reset is not supported for this account. Try Google Sign-In.");
        setIsLoading(false);
        return;
      }

      await signIn.prepareFirstFactor({
        strategy: "reset_password_email_code",
        emailAddressId: emailFactor.emailAddressId,
      });

      setResetStep("verify_reset");
    } catch (err) {
      console.error("Password reset error:", err);
      setError(err.errors?.[0]?.longMessage || err.errors?.[0]?.message || "Failed to initiate password reset.");
    } finally {
      setIsLoading(false);
    }
  };

  const handleResetSubmit = async (e) => {
    e.preventDefault();
    
    if (newPassword !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }

    setIsLoading(true);
    setError("");
    setSuccessMsg("");

    try {
      const result = await signIn.attemptFirstFactor({
        strategy: "reset_password_email_code",
        code: resetCode,
        password: newPassword,
      });

      if (result.status === "complete") {
        // Clerk automatically creates a session on password reset.
        // Since we want the user to explicitly sign in again, we sign them out immediately.
        await signOut();
        setResetStep("signin");
        setResetCode("");
        setNewPassword("");
        setConfirmPassword("");
        setSuccessMsg("Password successfully reset! Please sign in with your new password.");
      } else {
        setError("Password reset incomplete. Please try again.");
      }
    } catch (err) {
      console.error("Password reset verification error:", err);
      setError(err.errors?.[0]?.longMessage || err.errors?.[0]?.message || "Invalid verification code or password.");
    } finally {
      setIsLoading(false);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!isLoaded) return;

    setIsLoading(true);
    setError("");
    setSuccessMsg("");

    try {
      let loginIdentifier = identifier;

      // Synchronous suspension and username resolution check
      try {
        const statusCheck = await hitlService.checkStatus(identifier);
        if (statusCheck) {
          if (statusCheck.is_suspended) {
            setError("This account has been restricted.");
            setIsLoading(false);
            return;
          }
          if (statusCheck.user_name) {
            loginIdentifier = statusCheck.user_name;
          }
        }
      } catch (checkErr) {
        console.warn("Status check failed:", checkErr);
      }

      const result = await signIn.create({
        identifier: loginIdentifier,
        password,
      });

      if (result.status === "complete") {
        await setActive({ session: result.createdSessionId });
        window.location.href = "/";
      } else {
        setError("Sign in incomplete. Please try again.");
      }
    } catch (err) {
      console.error("Sign in error:", err);
      // Look for specific session errors
      const errorStr = JSON.stringify(err).toLowerCase();
      if (errorStr.includes("session_already_exists") || err.errors?.some(e => e.code === 'session_already_exists')) {
        window.location.href = "/";
        return;
      }
      
      const clerkMessage = err.errors?.[0]?.longMessage || err.errors?.[0]?.message || "";
      
      if (errorStr.includes("strategy_for_user_invalid") || clerkMessage.includes("verification strategy is not valid")) {
        setError("This account was created with Google. Please click 'Continue with Google' above.");
      } else if (clerkMessage.toLowerCase().includes("already signed in")) {
        window.location.href = "/";
      } else {
        setError(clerkMessage || "Invalid username or password");
      }
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-black flex items-center justify-center p-4 py-4">
      <div className="w-full max-w-[480px]">
        {/* Unified Card Container */}
        <div className="bg-[#0f0f0f] border border-gray-800 rounded-[32px] p-6 sm:px-10 sm:pt-6 sm:pb-3 shadow-2xl space-y-3 overflow-hidden">
          {resetStep === "forgot_password" ? (
            // Request Reset View
            <>
              <div className="space-y-0.5 text-center mb-6">
                <h1 className="text-xl font-bold text-white tracking-tight">Forgot password?</h1>
                <p className="text-gray-500 text-[9px]">Enter your email or username to reset your password.</p>
              </div>

              <div className="w-full mt-2">
                <form onSubmit={handleResetRequest} className="w-full space-y-4">
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

                  <div className="pt-4">
                    <button
                      type="submit"
                      disabled={isLoading}
                      className="bg-white text-black hover:bg-gray-100 font-bold py-2.5 w-full rounded-xl transition-all active:scale-[0.98] flex items-center justify-center text-sm disabled:opacity-70 disabled:cursor-not-allowed"
                    >
                      {isLoading ? "Sending..." : "Send Reset Code"}
                    </button>
                  </div>

                  <div className="flex items-center justify-center pt-3 pb-2">
                    <button 
                      type="button" 
                      onClick={() => { setResetStep("signin"); setError(""); }} 
                      className="text-gray-500 hover:text-gray-300 font-bold text-[11px] transition-colors"
                    >
                      Back to sign in
                    </button>
                  </div>
                </form>
              </div>
            </>
          ) : resetStep === "verify_reset" ? (
            // Reset Password View
            <>
              <div className="space-y-0.5 text-center mb-6">
                <h1 className="text-xl font-bold text-white tracking-tight">Reset your password</h1>
                <p className="text-gray-500 text-[9px]">Enter the verification code sent to your email</p>
              </div>

              <div className="w-full mt-2">
                <form onSubmit={handleResetSubmit} className="w-full space-y-4">
                  {error && (
                    <div className="text-red-400 text-[11px] text-center bg-red-500/10 rounded-xl p-2.5 border border-red-500/20 font-medium">
                      {error}
                    </div>
                  )}
                  
                  {/* Hidden field to hint password managers (prevents saving OTP as username) */}
                  <input type="text" name="username" value={identifier} autoComplete="username" className="hidden" readOnly />
                  
                  <div className="flex flex-col">
                    <label className="text-gray-400 font-medium text-[10px] mb-1">Verification Code</label>
                    <input
                      type="text"
                      value={resetCode}
                      onChange={(e) => setResetCode(e.target.value)}
                      placeholder="Enter 6-digit code"
                      autoComplete="one-time-code"
                      className="bg-[#1a1a1a] border border-gray-800 text-white focus:border-white rounded-xl h-9 transition-all px-4 w-full text-sm outline-none placeholder-gray-600"
                      required
                    />
                  </div>

                  <div className="flex flex-col">
                    <label className="text-gray-400 font-medium text-[10px] mb-1">New Password</label>
                    <div className="relative">
                      <input
                        type={showNewPassword ? "text" : "password"}
                        value={newPassword}
                        onChange={(e) => setNewPassword(e.target.value)}
                        placeholder="••••••••"
                        autoComplete="new-password"
                        className="bg-[#1a1a1a] border border-gray-800 text-white focus:border-white rounded-xl h-9 transition-all px-4 pr-10 w-full text-sm outline-none placeholder-gray-600"
                        required
                      />
                      <button
                        type="button"
                        onClick={() => setShowNewPassword(!showNewPassword)}
                        className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300 transition-colors focus:outline-none"
                      >
                        {showNewPassword ? <EyeOff size={14} /> : <Eye size={14} />}
                      </button>
                    </div>
                  </div>

                  <div className="flex flex-col">
                    <label className="text-gray-400 font-medium text-[10px] mb-1">Confirm Password</label>
                    <div className="relative">
                      <input
                        type={showConfirmPassword ? "text" : "password"}
                        value={confirmPassword}
                        onChange={(e) => setConfirmPassword(e.target.value)}
                        placeholder="••••••••"
                        autoComplete="new-password"
                        className="bg-[#1a1a1a] border border-gray-800 text-white focus:border-white rounded-xl h-9 transition-all px-4 pr-10 w-full text-sm outline-none placeholder-gray-600"
                        required
                      />
                      <button
                        type="button"
                        onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                        className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300 transition-colors focus:outline-none"
                      >
                        {showConfirmPassword ? <EyeOff size={14} /> : <Eye size={14} />}
                      </button>
                    </div>
                  </div>

                  <div className="pt-4">
                    <button
                      type="submit"
                      disabled={isLoading}
                      className="bg-white text-black hover:bg-gray-100 font-bold py-2.5 w-full rounded-xl transition-all active:scale-[0.98] flex items-center justify-center text-sm disabled:opacity-70 disabled:cursor-not-allowed"
                    >
                      {isLoading ? "Resetting..." : "Reset Password"}
                    </button>
                  </div>

                  <div className="flex items-center justify-center pt-3 pb-2">
                    <button 
                      type="button" 
                      onClick={() => { setResetStep("signin"); setError(""); }} 
                      className="text-gray-500 hover:text-gray-300 font-bold text-[11px] transition-colors"
                    >
                      Back to sign in
                    </button>
                  </div>
                </form>
              </div>
            </>
          ) : (
            // Standard Sign In View
            <>
              <div className="space-y-0.5 text-center">
                <h1 className="text-xl font-bold text-white tracking-tight">Welcome back</h1>
                <p className="text-gray-500 text-[9px]">Please enter your details to sign in</p>
              </div>

              <SocialLogin mode="signin" />

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
                  {successMsg && (
                    <div className="text-green-400 text-[11px] text-center bg-green-500/10 rounded-xl p-2.5 border border-green-500/20 font-medium">
                      {successMsg}
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
                <div className="flex items-center justify-between mb-1">
                  <label className="text-gray-400 font-medium text-[10px]">Password</label>
                  <button 
                    type="button" 
                    onClick={() => { setResetStep("forgot_password"); setError(""); }} 
                    className="text-gray-500 hover:text-white font-medium text-[10px] transition-colors"
                  >
                    Forgot password?
                  </button>
                </div>
                <div className="relative">
                  <input
                    type={showPassword ? "text" : "password"}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="••••••••"
                    className="bg-[#1a1a1a] border border-gray-800 text-white focus:border-white rounded-xl h-9 transition-all px-4 pr-10 w-full text-sm outline-none placeholder-gray-600"
                    required
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300 transition-colors focus:outline-none"
                  >
                    {showPassword ? <EyeOff size={14} /> : <Eye size={14} />}
                  </button>
                </div>
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
          </>
        )}
        </div>
      </div>
    </div>
  );
};

export default SignInPage;
