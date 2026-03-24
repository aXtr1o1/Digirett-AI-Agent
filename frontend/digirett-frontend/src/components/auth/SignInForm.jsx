// import React, { useEffect, useState } from 'react';
// import { useSignIn } from '@clerk/clerk-react';
// import { useNavigate, Link } from 'react-router-dom';
// import { Eye, EyeOff } from 'lucide-react';
// import LoadingSpinner from '../common/LoadingSpinner';

// const SignInForm = () => {
//   const { signIn, isLoaded, setActive } = useSignIn();
//   const navigate = useNavigate();

//   // ✅ Username or Email
//   const [identifier, setIdentifier] = useState('');
//   const [password, setPassword] = useState('');

//   const [rememberMe, setRememberMe] = useState(false);
//   const [showPassword, setShowPassword] = useState(false);
//   const [error, setError] = useState('');
//   const [isLoading, setIsLoading] = useState(false);

//   /* 🔁 Load remembered username */
//   useEffect(() => {
//     const saved = localStorage.getItem('rememberedIdentifier');
//     if (saved) {
//       setIdentifier(saved);
//       setRememberMe(true);
//     }
//   }, []);

//   /* 🔐 Username + Password login */
//   const handleSubmit = async (e) => {
//     e.preventDefault();
//     if (!isLoaded) return;

//     setIsLoading(true);
//     setError('');

//     try {
//       const result = await signIn.create({
//         identifier, // 👈 username OR email
//         password,
//       });

//       if (result.status === 'complete') {
//         await setActive({ session: result.createdSessionId });

//         if (rememberMe) {
//           localStorage.setItem('rememberedIdentifier', identifier);
//         } else {
//           localStorage.removeItem('rememberedIdentifier');
//         }

//         navigate('/chat', { replace: true });
//       } else {
//         setError('Sign in incomplete. Please try again.');
//       }
//     } catch (err) {
//       console.error('Sign in error:', err);
//       setError(err.errors?.[0]?.message || 'Invalid username or password');
//     } finally {
//       setIsLoading(false);
//     }
//   };

//   /* 🔵 Google Sign-In */
//   const handleGoogleSignIn = async () => {
//     if (!isLoaded) return;

//     try {
//       await signIn.authenticateWithRedirect({
//         strategy: 'oauth_google',
//         redirectUrl: '/sso-callback',
//         redirectUrlComplete: '/chat',
//       });
//     } catch (err) {
//       console.error('Google sign-in error:', err);
//       setError('Google sign-in failed');
//     }
//   };

//   return (
//     <div className="min-h-screen bg-black flex items-center justify-center px-4 py-12">
//       <div className="w-full max-w-md">

//         {/* Header */}
//         <div className="text-center mb-8">
//           <h1 className="text-3xl font-bold text-white mb-2">Welcome Back</h1>
//           <p className="text-gray-400">
//             Log in to your DigiRett Legal Assistance account
//           </p>
//         </div>

//         <form onSubmit={handleSubmit} className="space-y-6">

//           {error && (
//             <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-4">
//               <p className="text-red-400 text-sm text-center">{error}</p>
//             </div>
//           )}

//           {/* Google */}
//           <button
//             type="button"
//             onClick={handleGoogleSignIn}
//             disabled={isLoading}
//             className="w-full border border-gray-700 text-white py-3.5 rounded-xl
//                        hover:bg-gray-900 transition flex items-center justify-center gap-3"
//           >
//             <img
//               src="https://www.svgrepo.com/show/475656/google-color.svg"
//               alt="Google"
//               className="w-5 h-5"
//             />
//             Continue with Google
//           </button>

//           {/* Divider */}
//           <div className="flex items-center gap-4 my-4">
//             <div className="flex-1 h-px bg-gray-800" />
//             <span className="text-gray-500 text-sm">OR</span>
//             <div className="flex-1 h-px bg-gray-800" />
//           </div>

//           {/* Username */}
//           <div>
//             <label className="block text-sm font-medium text-white mb-2">
//               Username
//             </label>
//             <input
//               type="text"
//               value={identifier}
//               onChange={(e) => setIdentifier(e.target.value)}
//               placeholder="Enter your username"
//               className="w-full bg-[#1a1a1a] border border-gray-800 rounded-xl
//                          px-4 py-3.5 text-white placeholder-gray-500"
//               required
//               disabled={isLoading}
//             />
//           </div>

//           {/* Password */}
//           <div>
//             <label className="block text-sm font-medium text-white mb-2">
//               Password
//             </label>
//             <div className="relative">
//               <input
//                 type={showPassword ? 'text' : 'password'}
//                 value={password}
//                 onChange={(e) => setPassword(e.target.value)}
//                 placeholder="Enter your password"
//                 className="w-full bg-[#1a1a1a] border border-gray-800 rounded-xl
//                            px-4 py-3.5 text-white pr-12"
//                 required
//                 disabled={isLoading}
//               />
//               <button
//                 type="button"
//                 onClick={() => setShowPassword(!showPassword)}
//                 className="absolute right-4 top-1/2 -translate-y-1/2 text-gray-400"
//               >
//                 {showPassword ? <EyeOff size={20} /> : <Eye size={20} />}
//               </button>
//             </div>
//           </div>

//           {/* Remember + Forgot */}
//           <div className="flex items-center justify-between">
//             <label className="flex items-center gap-2 text-sm text-gray-300">
//               <input
//                 type="checkbox"
//                 checked={rememberMe}
//                 onChange={(e) => setRememberMe(e.target.checked)}
//                 className="w-4 h-4"
//                 disabled={isLoading}
//               />
//               Remember me
//             </label>

//             <Link
//               to="/forgot-password"
//               className="text-sm text-gray-400 hover:text-white"
//             >
//               Forgot password?
//             </Link>
//           </div>

//           {/* Submit */}
//           <button
//             type="submit"
//             disabled={isLoading || !identifier || !password}
//             className="w-full bg-white text-black font-semibold py-3.5 rounded-xl flex justify-center"
//           >
//             {isLoading ? <LoadingSpinner size="sm" /> : 'Login'}
//           </button>
//         </form>

//         {/* Sign Up */}
//         <div className="mt-8 text-center text-sm text-gray-400">
//           Don&apos;t have an account?{' '}
//           <Link to="/sign-up" className="text-white font-medium">
//             Create an account
//           </Link>
//         </div>
//       </div>
//     </div>
//   );
// };

// export default SignInForm;
import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import BackgroundLayer from "../common/BackgroundLayer";

const USERS = [
  { username: "admin1", password: "admin11" },
 
];

export default function SignInForm() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const navigate = useNavigate();

  const handleLogin = () => {
    const found = USERS.find(
      (u) => u.username === username && u.password === password
    );

    if (found) {
      localStorage.setItem("user", username);
      // after successful login
      localStorage.removeItem("conversationId"); // ⭐ clear previous chat
      navigate("/chat");
    } else {
      alert("Invalid credentials");
    }
  };

  return (
    <div className="relative flex h-screen w-screen overflow-hidden">
      {/* Chat-style background */}
      <BackgroundLayer theme="dark" />

      {/* Centered auth card */}
      <div className="relative z-10 flex flex-1 items-center justify-center px-4">
        <div className="w-full max-w-md">
          {/* Header */}
          <div className="mb-8 text-center">
            <h1 className="mb-2 text-3xl font-bold text-white">
              Welcome back to DigiRett
            </h1>
            <p className="mx-auto max-w-sm text-sm text-gray-400">
              Sign in to continue your conversation with your AI legal assistant.
            </p>
          </div>

          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleLogin();
            }}
            className="space-y-6 rounded-2xl border border-gray-800/70 bg-black/60 px-8 py-8 shadow-2xl backdrop-blur-xl"
          >
            <div className="space-y-4">
              <div className="text-left">
                <label className="mb-2 block text-sm font-medium text-gray-200">
                  Username
                </label>
                <input
                  placeholder="Enter your admin username"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  className="w-full rounded-xl border border-gray-800 bg-[#111111] px-4 py-3 text-sm text-white placeholder-gray-500 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/40"
                />
              </div>

              <div className="text-left">
                <label className="mb-2 block text-sm font-medium text-gray-200">
                  Password
                </label>
                <input
                  type="password"
                  placeholder="Enter your password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full rounded-xl border border-gray-800 bg-[#111111] px-4 py-3 text-sm text-white placeholder-gray-500 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/40"
                />
              </div>
            </div>

            <button
              type="submit"
              className="mt-2 w-full rounded-xl bg-blue-600 py-3 text-sm font-semibold text-white shadow-lg shadow-blue-500/30 transition hover:bg-blue-500"
            >
              Continue to chat
            </button>
          </form>

          <p className="mt-6 text-center text-xs text-gray-500">
            Digirett AI Agent
          </p>
        </div>
      </div>
    </div>
  );
}
