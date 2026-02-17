import React, { useState } from 'react';
import { useSignUp } from '@clerk/clerk-react';
import { useNavigate, Link } from 'react-router-dom';

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

  // STEP 1: CREATE ACCOUNT
  const handleSignUp = async (e) => {
    e.preventDefault();
    if (!isLoaded) return;

    setLoading(true);
    setError('');

    try {
      await signUp.create({
        username,                 // ✅ UNIQUE (Clerk enforces)
        emailAddress: email,
        password,
      });

      await signUp.prepareEmailAddressVerification({
        strategy: 'email_code',
      });

      setNeedsVerification(true);
    } catch (err) {
      console.log('Clerk signup error:', err);

      // ✅ Friendly error message
      setError(
        err.errors?.[0]?.message ||
        'Username or email already exists'
      );
    } finally {
      setLoading(false);
    }
  };

  // STEP 2: VERIFY EMAIL
  const handleVerify = async (e) => {
    e.preventDefault();
    if (!isLoaded) return;

    setLoading(true);
    setError('');

    try {
      const result = await signUp.attemptEmailAddressVerification({
        code,
      });

      console.log('Verification result:', result);

      if (result.createdSessionId) {
        await setActive({
          session: result.createdSessionId,
        });

        navigate('/chat', { replace: true });
      } else {
        setError('Verification failed. Try again.');
      }
    } catch (err) {
      console.log('Verification error:', err);
      setError(err.errors?.[0]?.message || 'Invalid or expired code');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-black flex items-center justify-center px-4">
      <div className="w-full max-w-md text-white">
        {!needsVerification ? (
          <form onSubmit={handleSignUp} className="space-y-4">
            <h1 className="text-3xl font-bold text-center">Sign Up</h1>

            {error && <p className="text-red-400 text-center">{error}</p>}

            <input
              placeholder="Username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full bg-[#1a1a1a] p-3 rounded-xl"
              required
            />

            <input
              type="email"
              placeholder="Email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full bg-[#1a1a1a] p-3 rounded-xl"
              required
            />

            <input
              type="password"
              placeholder="Password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full bg-[#1a1a1a] p-3 rounded-xl"
              required
            />

            <button
              type="submit"
              disabled={loading}
              className="w-full bg-white text-black py-3 rounded-xl font-semibold"
            >
              {loading ? 'Creating account…' : 'Create Account'}
            </button>

            <p className="text-center text-gray-400 text-sm">
              Already have an account?{' '}
              <Link to="/sign-in" className="text-white">
                Sign in
              </Link>
            </p>
          </form>
        ) : (
          <form onSubmit={handleVerify} className="space-y-4">
            <h1 className="text-2xl font-bold text-center">Verify Email</h1>

            {error && <p className="text-red-400 text-center">{error}</p>}

            <input
              placeholder="Verification code"
              value={code}
              onChange={(e) => setCode(e.target.value)}
              className="w-full bg-[#1a1a1a] p-3 rounded-xl"
              required
            />

            <button
              type="submit"
              disabled={loading}
              className="w-full bg-white text-black py-3 rounded-xl font-semibold"
            >
              Verify & Continue
            </button>
          </form>
        )}
      </div>
    </div>
  );
};

export default SignUpForm;
