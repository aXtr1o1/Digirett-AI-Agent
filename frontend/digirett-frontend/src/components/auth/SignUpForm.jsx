import React, { useState } from 'react';
import { useSignUp } from '@clerk/clerk-react';
import { useNavigate, Link } from 'react-router-dom';
import { Eye, EyeOff } from 'lucide-react';
import SocialLogin from './SocialLogin';

const SignUpForm = () => {
  const { signUp, isLoaded, setActive } = useSignUp();
  const navigate = useNavigate();

  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [code, setCode] = useState('');
  const [needsVerification, setNeedsVerification] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  
  // UI State
  const [showPassword, setShowPassword] = useState(false);

  // STEP 1: CREATE ACCOUNT
  const handleSignUp = async (e) => {
    e.preventDefault();
    if (!isLoaded) return;

    setLoading(true);
    setError('');

    try {
      const createdSignUp = await signUp.create({
        username,                 // ✅ UNIQUE (Clerk enforces)
        emailAddress: email,
        password,
      });

      // Clerk automatically sends a verification code for the primary email if required.
      // We check if it is already prepared before sending another one to avoid duplicate emails.
      const isEmailPrepared = createdSignUp.verifications?.emailAddress?.status === 'unverified';
      
      if (!isEmailPrepared) {
        await signUp.prepareEmailAddressVerification({
          strategy: 'email_code',
        });
      }

      setNeedsVerification(true);
    } catch (err) {
      console.log('Clerk signup error:', err);

      // ✅ Friendly error message
      setError(
        err.errors?.[0]?.longMessage ||
        err.errors?.[0]?.message ||
        'Username or email already exists'
      );
    } finally {
      setLoading(false);
    }
  };

  // STEP 1.5: RESEND CODE
  const handleResendCode = async () => {
    setError('');
    try {
      await signUp.prepareEmailAddressVerification({
        strategy: 'email_code',
      });
      alert('Verification code resent successfully!');
    } catch (err) {
      console.log('Resend error:', err);
      setError(err.errors?.[0]?.message || 'Failed to resend code');
    }
  };

  // STEP 2: VERIFY EMAIL
  const handleVerify = async (e) => {
    e.preventDefault();
    if (!isLoaded) return;

    setLoading(true);
    setError('');

    try {
      // Check if already verified in this session to prevent double submission error
      if (signUp.status === 'missing_requirements' && signUp.verifications.emailAddress.status === 'verified') {
        setError(`Missing requirements: ${signUp.missingFields?.join(', ')}`);
        setLoading(false);
        return;
      }

      const result = await signUp.attemptEmailAddressVerification({
        code,
      });

      console.log('Verification result:', result);

      if (result.status === 'complete') {
        await setActive({
          session: result.createdSessionId,
        });

        navigate('/', { replace: true });
      } else if (result.status === 'missing_requirements') {
        console.log('Missing fields:', result.missingFields);
        setError(`Verification successful, but missing required fields: ${result.missingFields?.join(', ')}`);
      } else {
        setError('Verification failed. Try again.');
      }
    } catch (err) {
      console.log('Verification error:', err);
      setError(err.errors?.[0]?.longMessage || err.errors?.[0]?.message || 'Invalid or expired code');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-black flex items-center justify-center p-4 py-4">
      <div className="w-full max-w-[480px]">
        {/* Unified Card Container */}
        <div className="bg-[#0f0f0f] border border-gray-800 rounded-[32px] p-6 sm:px-10 sm:pt-6 sm:pb-3 shadow-2xl space-y-3 overflow-hidden">
        {!needsVerification ? (
          <>
            <div className="space-y-0.5 text-center">
              <h1 className="text-xl font-bold text-white tracking-tight">Create an account</h1>
              <p className="text-gray-500 text-[9px]">Please enter your details to sign up</p>
            </div>

            <SocialLogin mode="signup" />

            <div className="relative mt-5 mb-5">
              <div className="absolute inset-0 flex items-center">
                <span className="w-full border-t border-gray-800/50"></span>
              </div>
              <div className="relative flex justify-center text-[8px] uppercase tracking-[0.2em]">
                <span className="bg-[#0f0f0f] px-3 text-gray-500 font-bold">Or continue with</span>
              </div>
            </div>

            <div className="w-full mt-2">
              <form onSubmit={handleSignUp} className="w-full space-y-3">
                {error && (
                  <div className="text-red-400 text-[11px] text-center bg-red-500/10 rounded-xl p-2.5 border border-red-500/20 font-medium">
                    {error}
                  </div>
                )}
                
                <div className="flex flex-col">
                  <label className="text-gray-400 font-medium text-[10px] mb-1">Username</label>
                  <input
                    type="text"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    placeholder="Choose a username"
                    className="bg-[#1a1a1a] border border-gray-800 text-white focus:border-white rounded-xl h-9 transition-all px-4 w-full text-sm outline-none placeholder-gray-600"
                    required
                  />
                </div>

                <div className="flex flex-col">
                  <label className="text-gray-400 font-medium text-[10px] mb-1">Email address</label>
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="Enter email address"
                    className="bg-[#1a1a1a] border border-gray-800 text-white focus:border-white rounded-xl h-9 transition-all px-4 w-full text-sm outline-none placeholder-gray-600"
                    required
                  />
                </div>

                <div className="flex flex-col">
                  <label className="text-gray-400 font-medium text-[10px] mb-1">Password</label>
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
                    disabled={loading}
                    className="bg-white text-black hover:bg-gray-100 font-bold py-2.5 w-full rounded-xl transition-all active:scale-[0.98] flex items-center justify-center text-sm disabled:opacity-70 disabled:cursor-not-allowed"
                  >
                    {loading ? "Creating account..." : "Create Account"}
                  </button>
                </div>

                <div className="flex items-center justify-center pt-3 pb-1">
                  <span className="text-gray-500 text-[11px] mr-1">Already have an account?</span>
                  <Link to="/sign-in" className="text-white font-bold text-[11px] hover:text-gray-300 transition-colors">
                    Sign in
                  </Link>
                </div>
              </form>
            </div>
          </>
        ) : (
          <>
            <div className="space-y-0.5 text-center mb-6">
              <h1 className="text-xl font-bold text-white tracking-tight">Verify Email</h1>
              <p className="text-gray-500 text-[9px]">Enter the verification code sent to your email</p>
            </div>

            <div className="w-full mt-2">
              <form onSubmit={handleVerify} className="w-full space-y-4">
                {error && (
                  <div className="text-red-400 text-[11px] text-center bg-red-500/10 rounded-xl p-2.5 border border-red-500/20 font-medium">
                    {error}
                  </div>
                )}
                
                <div className="flex flex-col">
                  <label className="text-gray-400 font-medium text-[10px] mb-1">Verification Code</label>
                  <input
                    type="text"
                    value={code}
                    onChange={(e) => setCode(e.target.value)}
                    placeholder="Enter 6-digit code"
                    className="bg-[#1a1a1a] border border-gray-800 text-white focus:border-white rounded-xl h-9 transition-all px-4 w-full text-sm outline-none placeholder-gray-600"
                    required
                  />
                </div>

                <div className="pt-4">
                  <button
                    type="submit"
                    disabled={loading}
                    className="bg-white text-black hover:bg-gray-100 font-bold py-2.5 w-full rounded-xl transition-all active:scale-[0.98] flex items-center justify-center text-sm disabled:opacity-70 disabled:cursor-not-allowed"
                  >
                    {loading ? "Verifying..." : "Verify & Continue"}
                  </button>
                </div>

                <div className="flex items-center justify-center pt-3 pb-2">
                  <button 
                    type="button" 
                    onClick={handleResendCode}
                    className="text-gray-500 hover:text-gray-300 font-bold text-[11px] transition-colors"
                  >
                    Didn't receive a code? Resend
                  </button>
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

export default SignUpForm;