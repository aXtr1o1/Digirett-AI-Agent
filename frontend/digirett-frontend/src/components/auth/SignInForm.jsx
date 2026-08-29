import React, { useEffect, useState } from 'react';
import { useSignIn, useClerk, useAuth, useUser } from '@clerk/clerk-react';
import { useNavigate, Link, useLocation } from 'react-router-dom';
import { Eye, EyeOff, AlertTriangle } from 'lucide-react';
import hitlService from '../services/hitlService';
// We'll use a simple fallback if LoadingSpinner isn't available
// import LoadingSpinner from '../common/LoadingSpinner';

const SignInForm = () => {
  const { signIn, isLoaded, setActive } = useSignIn();
  const { signOut } = useClerk();
  const { isSignedIn } = useAuth();
  const { user } = useUser();
  const navigate = useNavigate();
  const location = useLocation();

  // ✅ Username or Email
  const [identifier, setIdentifier] = useState('');
  const [password, setPassword] = useState('');

  const [rememberMe, setRememberMe] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  // 🚀 FAIL-SAFE: Redirect if already logged in (regular users)
  useEffect(() => {
    if (isLoaded && isSignedIn && user) {
      const role = user.publicMetadata?.role;
      if (role !== 'suspended') {
        console.log('Failsafe: User is signed in, redirecting to home...');
        navigate('/');
      }
    }
  }, [isLoaded, isSignedIn, user, navigate]);

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
      // 🛡️ 1. PRE-LOGIN SUSPENSION CHECK
      // We check our DB status before even trying to authenticate with Clerk
      try {
        const statusCheck = await hitlService.checkStatus(identifier);
        if (statusCheck) {
          if (statusCheck.status === 'case_mismatch') {
            setError('Invalid username or password');
            setIsLoading(false);
            return;
          }
          if (statusCheck.is_suspended) {
            setError('This account has been restricted. Please contact support@digirett.com for more information.');
            setIsLoading(false);
            return;
          }
        }
      } catch (checkErr) {
        // We log but don't block if the status check fails (e.g. backend down)
        console.warn('Suspension check failed, proceeding to auth:', checkErr);
      }

      // 🛡️ 2. CLERK AUTHENTICATION
      const result = await signIn.create({
        identifier, // 👈 username OR email
        password,
      });

      if (result.status === 'complete') {
        await setActive({ session: result.createdSessionId });

        // The useEffect guard will handle the redirection or suspension check
        // once the session is set and user object is loaded.
        if (rememberMe) {
          localStorage.setItem('rememberedIdentifier', identifier);
        } else {
          localStorage.removeItem('rememberedIdentifier');
        }
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

        {/* Google Login - PRIMARY ACTION */}
        <div className="mb-6">
          <button
            type="button"
            onClick={() => signIn.authenticateWithRedirect({
              strategy: "oauth_google",
              redirectUrl: "/",
              redirectUrlComplete: "/"
            })}
            className="w-full bg-white text-black font-bold py-4 rounded-2xl flex items-center justify-center gap-3 hover:bg-gray-100 transition-all shadow-xl shadow-white/5"
          >
            <svg className="w-5 h-5" viewBox="0 0 24 24">
              <path
                fill="currentColor"
                d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
              />
              <path
                fill="currentColor"
                d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
              />
              <path
                fill="currentColor"
                d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z"
              />
              <path
                fill="currentColor"
                d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
              />
            </svg>
            <span className="text-sm">Continue with Google</span>
          </button>

          {/* Divider */}
          <div className="flex items-center gap-4 my-8">
            <div className="h-px bg-gray-800 flex-1"></div>
            <span className="text-gray-500 text-[10px] font-black uppercase tracking-[0.2em]">OR USE EMAIL</span>
            <div className="h-px bg-gray-800 flex-1"></div>
          </div>
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
              Username
            </label>
            <input
              type="text"
              value={identifier}
              onChange={(e) => setIdentifier(e.target.value)}
              placeholder="Enter your username"
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
            className="w-full bg-white text-black font-semibold py-3.5 rounded-xl flex justify-center hover:bg-gray-100 transition-all"
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