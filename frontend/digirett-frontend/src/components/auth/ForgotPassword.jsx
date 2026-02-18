import React, { useState } from 'react';
import { useSignIn } from '@clerk/clerk-react';
import { useNavigate, Link } from 'react-router-dom';

const ForgotPassword = () => {
  const { signIn, isLoaded } = useSignIn();
  const navigate = useNavigate();

  const [step, setStep] = useState('email'); // email | verify
  const [email, setEmail] = useState('');
  const [code, setCode] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  if (!isLoaded) return null;

  /* STEP 1 — Send reset code */
  const sendResetCode = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      await signIn.create({
        strategy: 'reset_password_email_code',
        identifier: email,
      });
      setStep('verify');
    } catch (err) {
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
      await signIn.attemptFirstFactor({
        strategy: 'reset_password_email_code',
        code,
        password: newPassword,
      });

      navigate('/sign-in');
    } catch (err) {
      setError(err.errors?.[0]?.message || 'Invalid code or password');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-black flex items-center justify-center px-4">
      <div className="w-full max-w-md bg-[#0f0f0f] p-8 rounded-2xl border border-gray-800">
        <h1 className="text-2xl font-bold text-white mb-6">
          Reset Password
        </h1>

        {error && (
          <div className="mb-4 text-sm text-red-400 bg-red-500/10 border border-red-500/30 rounded-lg p-3">
            {error}
          </div>
        )}

        {step === 'email' ? (
          <form onSubmit={sendResetCode} className="space-y-4">
            <input
              type="email"
              placeholder="Enter your email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full bg-[#1a1a1a] border border-gray-800 rounded-xl px-4 py-3 text-white focus:outline-none focus:ring-2 focus:ring-white/20"
              required
              disabled={loading}
            />

            <button
              type="submit"
              disabled={loading}
              className="w-full bg-white text-black font-semibold py-3 rounded-xl disabled:opacity-50"
            >
              Send reset code
            </button>
          </form>
        ) : (
          <form onSubmit={resetPassword} className="space-y-4">
            <input
              placeholder="Enter reset code"
              value={code}
              onChange={(e) => setCode(e.target.value)}
              className="w-full bg-[#1a1a1a] border border-gray-800 rounded-xl px-4 py-3 text-white"
              required
              disabled={loading}
            />

            <input
              type="password"
              placeholder="New password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              className="w-full bg-[#1a1a1a] border border-gray-800 rounded-xl px-4 py-3 text-white"
              required
              disabled={loading}
            />

            <button
              type="submit"
              disabled={loading}
              className="w-full bg-white text-black font-semibold py-3 rounded-xl disabled:opacity-50"
            >
              Reset password
            </button>
          </form>
        )}

        <div className="mt-6 text-center text-sm text-gray-400">
          <Link to="/sign-in" className="hover:text-white">
            Back to login
          </Link>
        </div>
      </div>
    </div>
  );
};

export default ForgotPassword;
