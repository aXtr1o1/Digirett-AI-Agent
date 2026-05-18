import React from 'react';
import { useSignUp, useSignIn } from '@clerk/clerk-react';
import { FcGoogle } from 'react-icons/fc';

const SocialLogin = ({ mode = 'signin' }) => {
  const { signUp, isLoaded: signUpLoaded } = useSignUp();
  const { signIn, isLoaded: signInLoaded } = useSignIn();

  const handleGoogleLogin = async () => {
    if (mode === 'signup') {
      if (!signUpLoaded) return;
      try {
        console.log("[SocialLogin] Initiating Google OAuth Sign-Up...");
        await signUp.authenticateWithRedirect({
          strategy: 'oauth_google',
          redirectUrl: `${window.location.origin}/sso-callback`,
          redirectUrlComplete: `${window.location.origin}/`,
        });
      } catch (err) {
        console.error("Social signup error:", err);
      }
    } else {
      if (!signInLoaded) return;
      try {
        console.log("[SocialLogin] Initiating Google OAuth Sign-In...");
        await signIn.authenticateWithRedirect({
          strategy: 'oauth_google',
          redirectUrl: `${window.location.origin}/sso-callback`,
          redirectUrlComplete: `${window.location.origin}/`,
        });
      } catch (err) {
        console.error("Social signin error:", err);
      }
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
