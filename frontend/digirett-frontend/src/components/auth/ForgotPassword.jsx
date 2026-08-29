import React, { useState } from 'react';
import { useSignIn, useAuth, useClerk } from '@clerk/clerk-react';
import { useNavigate, Link } from 'react-router-dom';
import { Mail, KeyRound, ArrowLeft, Loader2, CheckCircle2 } from 'lucide-react';

const ForgotPassword = () => {
  const { signIn, isLoaded, setActive } = useSignIn();
  const { isSignedIn } = useAuth();
  const { signOut } = useClerk();
  const navigate = useNavigate();

  const [step, setStep] = useState('email'); // email | verify | success
  const [email, setEmail] = useState('');
  const [code, setCode] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  if (!isLoaded) return null;

  // If already signed in, don't show the form (prevents "Session already exists" error)
  if (isSignedIn) {
    return (
      <div className="min-h-screen bg-black flex items-center justify-center px-4">
        <div className="w-full max-w-md bg-[#0f0f0f] p-10 rounded-3xl border border-gray-800 text-center">
          <h2 className="text-2xl font-bold text-white mb-4">You're Already Signed In</h2>
          <p className="text-gray-400 mb-8">You don't need to reset your password if you already have access to your account. Please sign out first if you want to perform a reset.</p>
          <div className="space-y-4">
            <button
              onClick={() => navigate('/')}
              className="w-full bg-white text-black font-bold py-4 rounded-2xl"
            >
              Go to Dashboard
            </button>
            <button
              onClick={() => signOut()}
              className="w-full bg-transparent border border-red-500 text-red-500 font-bold py-4 rounded-2xl hover:bg-red-500/10 transition-all"
            >
              Log Out to Reset Password
            </button>
          </div>
        </div>
      </div>
    );
  }

  /* STEP 1 — Send reset code */
  const sendResetCode = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      const si = await signIn.create({
        strategy: 'reset_password_email_code',
        identifier: email,
      });

      setStep('verify');
    } catch (err) {
      console.error('Send code error:', err);

      // Broadened check for "already signed in" or "session exists"
      const errorMsg = JSON.stringify(err).toLowerCase();
      const isAlreadySignedIn = errorMsg.includes('signed in') || errorMsg.includes('session_already_exists');

      if (isAlreadySignedIn) {
        setError('Active session detected. Logging you out to allow password reset...');
        setTimeout(async () => {
          try {
            await signOut();
            window.location.href = '/forgot-password'; // Hard redirect to clear all state
          } catch (e) {
            window.location.reload();
          }
        }, 1000);
        return;
      }

      setError(err.errors?.[0]?.message || 'Failed to send reset code');
    } finally {
      setLoading(false);
    }
  };

  /* STEP 2 — Verify code + reset password */
  const resetPassword = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      const result = await signIn.attemptFirstFactor({
        strategy: 'reset_password_email_code',
        code,
        password: newPassword,
      });

      if (result.status === 'complete') {
        alert('Password updated successfully!');
        // Pass credentials to the sign-in page via state
        navigate('/sign-in', {
          state: {
            identifier: email,
            password: newPassword,
            message: 'Your password has been updated. Click login to continue.'
          }
        });
      } else {
        setError('Incomplete status: ' + result.status);
      }
    } catch (err) {
      console.error('Reset error:', err);
      setError(err.errors?.[0]?.message || 'Invalid code or password');
    } finally {
      setLoading(false);
    }
  };

  if (step === 'success') {
    return (
      <div className="min-h-screen bg-black flex items-center justify-center px-4">
        <div className="w-full max-w-md bg-[#0f0f0f] p-10 rounded-3xl border border-gray-800 text-center animate-in fade-in zoom-in duration-300">
          <div className="inline-flex items-center justify-center h-20 w-20 rounded-full bg-green-500/10 mb-6">
            <CheckCircle2 className="h-10 w-10 text-green-500" />
          </div>
          <h2 className="text-2xl font-bold text-white mb-2">Password Reset!</h2>
          <p className="text-gray-400 mb-8">Your password has been successfully updated. You are now logged in.</p>
          <button
            onClick={() => navigate('/chat')}
            className="w-full bg-white text-black font-bold py-4 rounded-2xl hover:bg-gray-100 transition-all shadow-lg"
          >
            Go to Chat
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-black flex items-center justify-center px-4">
      <div className="w-full max-w-md bg-[#0f0f0f] p-8 md:p-10 rounded-3xl border border-gray-800 shadow-2xl">
        <div className="mb-8">
          <Link to="/sign-in" className="inline-flex items-center text-sm text-gray-500 hover:text-white transition-colors gap-2 mb-6">
            <ArrowLeft className="h-4 w-4" />
            Back to login
          </Link>
          <h1 className="text-3xl font-bold text-white mb-2">
            {step === 'email' ? 'Forgot Password?' : 'Reset Password'}
          </h1>
          <p className="text-gray-400 text-sm">
            {step === 'email'
              ? 'Enter your email and we\'ll send you a recovery code.'
              : `We've sent a 6-digit code to ${email}`}
          </p>
        </div>

        {error && (
          <div className="mb-6 text-sm text-red-400 bg-red-500/10 border border-red-500/30 rounded-xl p-4 flex items-start gap-3">
            <div className="h-2 w-2 rounded-full bg-red-500 mt-1.5 shrink-0"></div>
            {error}
          </div>
        )}

        {step === 'email' ? (
          <form onSubmit={sendResetCode} className="space-y-6">
            <div className="space-y-2">
              <label className="text-xs font-bold text-gray-500 uppercase tracking-widest px-1">Email Address</label>
              <div className="relative">
                <input
                  type="email"
                  placeholder="name@example.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full bg-[#1a1a1a] border border-gray-800 rounded-2xl px-5 py-4 text-white focus:outline-none focus:ring-2 focus:ring-white/10 transition-all pl-12"
                  required
                  disabled={loading}
                />
                <Mail className="absolute left-4 top-1/2 -translate-y-1/2 h-5 w-5 text-gray-600" />
              </div>
            </div>

            <button
              type="submit"
              disabled={loading || !email}
              className="w-full bg-white text-black font-bold py-4 rounded-2xl disabled:opacity-50 hover:bg-gray-100 transition-all flex items-center justify-center gap-2"
            >
              {loading ? <Loader2 className="h-5 w-5 animate-spin" /> : null}
              Send Recovery Code
            </button>
          </form>
        ) : (
          <form onSubmit={resetPassword} className="space-y-6">
            {/* Hidden field to help browser identify the user account being reset */}
            <input type="text" name="username" value={email} autoComplete="username" className="hidden" readOnly />

            <div className="space-y-2">
              <label className="text-xs font-bold text-gray-500 uppercase tracking-widest px-1">Recovery Code</label>
              <div className="relative">
                <input
                  name="code"
                  placeholder="Enter 6-digit code"
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                  autoComplete="one-time-code"
                  className="w-full bg-[#1a1a1a] border border-gray-800 rounded-2xl px-5 py-4 text-white focus:outline-none focus:ring-2 focus:ring-white/10 transition-all pl-12"
                  required
                  disabled={loading}
                />
                <KeyRound className="absolute left-4 top-1/2 -translate-y-1/2 h-5 w-5 text-gray-600" />
              </div>
            </div>

            <div className="space-y-2">
              <label className="text-xs font-bold text-gray-500 uppercase tracking-widest px-1">New Password</label>
              <input
                type="password"
                name="new-password"
                placeholder="At least 8 characters"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                autoComplete="new-password"
                className="w-full bg-[#1a1a1a] border border-gray-800 rounded-2xl px-5 py-4 text-white focus:outline-none focus:ring-2 focus:ring-white/10 transition-all"
                required
                disabled={loading}
              />
            </div>

            <button
              type="submit"
              disabled={loading || !code || !newPassword}
              className="w-full bg-white text-black font-bold py-4 rounded-2xl disabled:opacity-50 hover:bg-gray-100 transition-all flex items-center justify-center gap-2"
            >
              {loading ? <Loader2 className="h-5 w-5 animate-spin" /> : null}
              Reset Password
            </button>
          </form>
        )}
      </div>
    </div>
  );
};

export default ForgotPassword;
