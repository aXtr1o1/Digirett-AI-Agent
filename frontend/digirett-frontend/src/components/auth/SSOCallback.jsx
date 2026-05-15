import React, { useEffect, useState } from 'react';
import { useClerk, useSignUp, useSignIn } from '@clerk/clerk-react';
import { useNavigate } from 'react-router-dom';

const SSOCallback = () => {
  const { handleRedirectCallback } = useClerk();
  const { signUp, isLoaded: signUpLoaded, setActive: setSignUpActive } = useSignUp();
  const { signIn, isLoaded: signInLoaded, setActive: setSignInActive } = useSignIn();
  const navigate = useNavigate();
  const [error, setError] = useState(null);

  useEffect(() => {
    const processCallback = async () => {
      try {
        // 1. Let Clerk handle the low-level OAuth handshake
        // This will populate the signUp or signIn objects
          await handleRedirectCallback({
            afterSignInUrl: '/',
            afterSignUpUrl: '/',
            continueSignUpUrl: '/sign-up',
          });

        // 2. Check for missing requirements (specifically Username)
        if (signUpLoaded && signUp && signUp.status === 'missing_requirements') {
          if (signUp.missingFields.includes('username')) {
            console.log("Auto-generating username from email...");
            
            // Derive username from email prefix
            const email = signUp.emailAddress || '';
            let derivedUsername = email.split('@')[0].toLowerCase().replace(/[^a-z0-9]/g, '');
            
            // Add a small random suffix to avoid collisions
            if (derivedUsername.length < 3) derivedUsername += Math.floor(Math.random() * 1000);

            try {
              const result = await signUp.update({ username: derivedUsername });
              
              if (result.status === 'complete') {
                await setSignUpActive({ session: result.createdSessionId });
                navigate('/');
                return;
              }
            } catch (updateErr) {
              console.error("Failed to auto-set username:", updateErr);
              // If it fails (e.g. username taken), fallback to the sign-up page
              navigate('/sign-up');
              return;
            }
          }
        }

        // 3. Fallback redirect if everything else is handled
        navigate('/');
      } catch (err) {
        console.error("SSO Callback processing error:", err);
        setError(err.message);
        // On error, take them back to sign-in after a short delay
        setTimeout(() => navigate('/sign-in'), 3000);
      }
    };

    if (signUpLoaded && signInLoaded) {
      processCallback();
    }
  }, [handleRedirectCallback, signUp, signUpLoaded, signIn, signInLoaded, setSignUpActive, setSignInActive, navigate]);

  if (error) {
    return (
      <div className="min-h-screen bg-black flex flex-col items-center justify-center p-6 text-center">
        <h2 className="text-xl font-bold text-red-500 mb-2">Authentication Error</h2>
        <p className="text-gray-400">{error}</p>
        <p className="text-gray-500 mt-4 text-sm">Redirecting to login...</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-black flex flex-col items-center justify-center p-6 text-center">
      <div className="relative mb-8">
        <div className="absolute inset-0 bg-white/10 rounded-full animate-ping scale-150"></div>
        <div className="relative bg-[#0f0f0f] p-6 rounded-full border border-gray-800 shadow-2xl">
          <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-white"></div>
        </div>
      </div>
      <h2 className="text-2xl font-bold text-white mb-2 animate-pulse">
        Completing secure login...
      </h2>
      <p className="text-gray-400">Verifying your identity and setting up your profile.</p>
    </div>
  );
};

export default SSOCallback;
