import React from 'react';
import { useSignUp } from '@clerk/clerk-react';
import { FcGoogle } from 'react-icons/fc';

const SocialLogin = () => {
  const { signUp, isLoaded } = useSignUp();

  const handleGoogleLogin = async () => {
    if (!isLoaded) return;

    try {
      // ✅ Universal Clerk OAuth flow (Sign Up version):
      // 1. Redirect to /sso-callback to process the auth
      // 2. Redirect to /chat (or customized in SSOCallback)
      // Note: useSignUp is better for universal buttons because it handles new users
      // without 'Account not found' errors, while existing users are auto-signed in.
      await signUp.authenticateWithRedirect({
        strategy: 'oauth_google',
        redirectUrl: `${window.location.origin}/sso-callback`,
        redirectUrlComplete: `${window.location.origin}/`,
      });
    } catch (err) {
      console.error("Social login error:", err);
    }
  };

  return (
    <button
      onClick={handleGoogleLogin}
      className="w-full flex items-center justify-center gap-3 bg-[#1a1a1a] hover:bg-[#252525] text-white border border-gray-800 rounded-xl py-3 px-4 transition-all duration-200 font-medium group shadow-lg"
    >
      <FcGoogle className="text-2xl group-hover:scale-110 transition-transform" />
      <span>Continue with Google</span>
    </button>
  );
};

export default SocialLogin;
