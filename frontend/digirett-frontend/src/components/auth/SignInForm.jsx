import React, { useEffect, useState } from 'react';
import { useSignIn, useClerk, useAuth } from '@clerk/clerk-react';
import { useNavigate, Link, useLocation } from 'react-router-dom';
import { Eye, EyeOff } from 'lucide-react';
// We'll use a simple fallback if LoadingSpinner isn't available
// import LoadingSpinner from '../common/LoadingSpinner';

const SignInForm = () => {
  const { signIn, isLoaded, setActive } = useSignIn();
  const { signOut } = useClerk();
  const { isSignedIn } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  // ✅ Username or Email
  const [identifier, setIdentifier] = useState('');
  const [password, setPassword] = useState('');

  const [rememberMe, setRememberMe] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  // 🚀 FAIL-SAFE: If the user is already signed in, whisk them away immediately
  useEffect(() => {
    if (isLoaded && isSignedIn) {
      console.log('Failsafe: User is signed in, redirecting to home...');
      navigate('/');
    }
  }, [isLoaded, isSignedIn, navigate]);

  /* 🔁 Load remembered username or incoming reset state */
  useEffect(() => {
    // 1. Check for incoming credentials from Forgot Password
    if (location.state?.identifier) {
      setIdentifier(location.state.identifier);
      if (location.state.password) {
        setPassword(location.state.password);
      }
      if (location.state.message) {
        // Show the success message from forgot password as a temporary non-error notice
        setError(''); 
      }
      return;
    }

    // 2. Fallback to local storage remember me
    const saved = localStorage.getItem('rememberedIdentifier');
    if (saved) {
      setIdentifier(saved);
      setRememberMe(true);
    }
  }, [location.state]);

  /* 🔐 Username + Password login */
  /* 🔑 Password Reset Initiation */
  const handleForgotPassword = (e) => {
    e.preventDefault();
    navigate('/forgot-password');
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!isLoaded) return;

    //  If already signed in, don't even try to create a new session
    if (isSignedIn) {
      window.location.href = '/';
      return;
    }

    setIsLoading(true);
    setError('');

    try {
      const result = await signIn.create({
        identifier, // 👈 username OR email
        password,
      });

      if (result.status === 'complete') {
        await setActive({ session: result.createdSessionId });
        
        //  Force immediate redirect to the role-based dashboard
        navigate('/'); 

        if (rememberMe) {
          localStorage.setItem('rememberedIdentifier', identifier);
        } else {
          localStorage.removeItem('rememberedIdentifier');
        }

        navigate('/chat', { replace: true });
      } else {
        setError('Sign in incomplete. Please try again.');
      }
    } catch (err) {
      console.error('Sign in error:', err);
      
      // 🔍 Thorough check for existing session errors
      const errorStr = JSON.stringify(err).toLowerCase();
      const isSessionError = 
        errorStr.includes('signed in') || 
        errorStr.includes('session_already_exists') || 
        err.errors?.some(e => e.code === 'session_already_exists');

      if (isSessionError) {
        console.log('Session already exists, forcing hard redirect...');
        window.location.href = '/'; 
        return;
      }
      
      setError(err.errors?.[0]?.message || 'Invalid username or password');
    } finally {
      setIsLoading(false);
    }
  };

  if (isSignedIn) {
    return (
      <div className="min-h-screen bg-black flex items-center justify-center px-4">
        <div className="w-full max-w-md bg-[#0f0f0f] p-10 rounded-3xl border border-gray-800 text-center animate-in fade-in duration-300">
          <h2 className="text-2xl font-bold text-white mb-4">Session Already Exists</h2>
          <p className="text-gray-400 mb-8">You are currently signed in. To log in with a different account or reset your password, please sign out first.</p>
          <div className="space-y-4">
            <button
              onClick={() => navigate('/')}
              className="w-full bg-white text-black font-bold py-4 rounded-2xl hover:bg-gray-100 transition-all"
            >
              Go to Dashboard
            </button>
            <button
              onClick={() => signOut()}
              className="w-full bg-transparent border border-red-500 text-red-500 font-bold py-4 rounded-2xl hover:bg-red-500/10 transition-all"
            >
              Log Out Current Session
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-black flex items-center justify-center px-4 py-12">
      <div className="w-full max-w-md">

        {/* Header */}
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-white mb-2">Welcome Back</h1>
          <p className="text-gray-400">
            Log in to your DigiRett Legal Assistance account
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-6">

          {error && (
            <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-4">
              <p className="text-red-400 text-sm text-center">{error}</p>
            </div>
          )}

          {/* Username */}
          <div>
            <label className="block text-sm font-medium text-white mb-2">
              Username or Email
            </label>
            <input
              type="text"
              value={identifier}
              onChange={(e) => setIdentifier(e.target.value)}
              placeholder="Enter your username or email"
              className="w-full bg-[#1a1a1a] border border-gray-800 rounded-xl
                         px-4 py-3.5 text-white placeholder-gray-500"
              required
              disabled={isLoading}
            />
          </div>

          {/* Password */}
          <div>
            <label className="block text-sm font-medium text-white mb-2">
              Password
            </label>
            <div className="relative">
              <input
                type={showPassword ? 'text' : 'password'}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Enter your password"
                className="w-full bg-[#1a1a1a] border border-gray-800 rounded-xl
                           px-4 py-3.5 text-white pr-12"
                required
                disabled={isLoading}
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-4 top-1/2 -translate-y-1/2 text-gray-400"
              >
                {showPassword ? <EyeOff size={20} /> : <Eye size={20} />}
              </button>
            </div>
          </div>

          {/* Remember + Forgot */}
          <div className="flex items-center justify-between">
            <label className="flex items-center gap-2 text-sm text-gray-300">
              <input
                type="checkbox"
                checked={rememberMe}
                onChange={(e) => setRememberMe(e.target.checked)}
                className="w-4 h-4"
                disabled={isLoading}
              />
              Remember me
            </label>

            <button
              type="button"
              onClick={handleForgotPassword}
              className="text-sm text-gray-400 hover:text-white transition-colors"
              disabled={isLoading}
            >
              Forgot password?
            </button>
          </div>

          {/* Submit */}
          <button
            type="submit"
            disabled={isLoading || !identifier || !password}
            className="w-full bg-white text-black font-semibold py-3.5 rounded-xl flex justify-center"
          >
            {isLoading ? 'Loading...' : 'Login'}
          </button>
        </form>

        {/* Sign Up */}
        <div className="mt-8 text-center text-sm text-gray-400">
          Don't have an account?{' '}
          <Link to="/sign-up" className="text-white font-medium">
            Create an account
          </Link>
        </div>
      </div>
    </div>
  );
};

export default SignInForm;