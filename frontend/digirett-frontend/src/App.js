// import React from "react";
// import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
// import { SignedIn, SignedOut } from "@clerk/clerk-react";

// import ClerkWithRouter from "./providers/ClerkWithRouter";
// import ProtectedRoute from "./components/auth/ProtectedRoute";

// import SignInPage from "./pages/SignInPage";
// import SignUpPage from "./pages/SignUpPage";
// import ForgotPasswordPage from "./pages/ForgotPasswordPage";
// import ChatPage from "./pages/ChatPage";
// import SSOCallback from "./components/auth/SSOCallback";

// function App() {
//   return (
//     <BrowserRouter>
//       <ClerkWithRouter>
//         <Routes>

//           {/* ================= AUTH PAGES ================= */}

//           {/* Sign In */}
//           <Route
//             path="/sign-in"
//             element={
//               <>
//                 <SignedIn>
//                   <Navigate to="/chat" replace />
//                 </SignedIn>
//                 <SignedOut>
//                   <SignInPage />
//                 </SignedOut>
//               </>
//             }
//           />

//           {/* Sign Up */}
//           <Route
//             path="/sign-up"
//             element={
//               <>
//                 <SignedIn>
//                   <Navigate to="/chat" replace />
//                 </SignedIn>
//                 <SignedOut>
//                   <SignUpPage />
//                 </SignedOut>
//               </>
//             }
//           />

//           {/* Forgot Password */}
//           <Route
//             path="/forgot-password"
//             element={
//               <>
//                 <SignedIn>
//                   <Navigate to="/chat" replace />
//                 </SignedIn>
//                 <SignedOut>
//                   <ForgotPasswordPage />
//                 </SignedOut>
//               </>
//             }
//           />

//           {/* OAuth callback */}
//           <Route path="/sso-callback" element={<SSOCallback />} />


//           {/* ================= PROTECTED ================= */}

//           <Route
//             path="/chat"
//             element={
//               <ProtectedRoute>
//                 <ChatPage />
//               </ProtectedRoute>
//             }
//           />


//           {/* ================= ROOT ================= */}

//           <Route
//             path="/"
//             element={
//               <>
//                 <SignedIn>
//                   <Navigate to="/chat" replace />
//                 </SignedIn>
//                 <SignedOut>
//                   <Navigate to="/sign-in" replace />
//                 </SignedOut>
//               </>
//             }
//           />

//           {/* fallback */}
//           <Route path="*" element={<Navigate to="/" replace />} />

//         </Routes>
//       </ClerkWithRouter>
//     </BrowserRouter>
//   );
// }

// export default App;
import React, { useEffect } from "react";   // ✅ add useEffect here
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";

import SignInPage from "./pages/SignInPage";
import ChatPage from "./pages/ChatPage";
import ProtectedRoute from "./components/auth/ProtectedRoute";

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/sign-in" element={<SignInPage />} />

        <Route
          path="/chat"
          element={
            <ProtectedRoute>
              <ChatPage />
            </ProtectedRoute>
          }
        />

        <Route path="/" element={<Navigate to="/sign-in" />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;

