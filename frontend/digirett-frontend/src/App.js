import React from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { SignedIn, SignedOut } from "@clerk/clerk-react";

import ClerkWithRouter from "./providers/ClerkWithRouter";
import ProtectedRoute from "./components/auth/ProtectedRoute";
import RoleGuard from "./components/auth/RoleGuard";

import SignInPage from "./pages/SignInPage";
import SignUpPage from "./pages/SignUpPage";
import ChatPage from "./pages/ChatPage";
import InvitePage from "./pages/InvitePage";
import AdminDashboard from "./pages/AdminDashboard";
import LawyerDashboard from "./pages/LawyerDashboard";
import TicketDetailsPage from "./pages/TicketDetailsPage";
import ForgotPasswordPage from "./pages/ForgotPasswordPage";
import { useUser, useAuth } from "@clerk/clerk-react";

const HomeRedirect = () => {
  const { isSignedIn, isLoaded: authLoaded } = useAuth();

  if (!authLoaded) {
    return (
      <div className="min-h-screen bg-black flex items-center justify-center">
        <div className="animate-spin rounded-full h-8 w-8 border-t-2 border-b-2 border-white"></div>
      </div>
    );
  }

  if (!isSignedIn) return <Navigate to="/sign-in" replace />;
  
  // 🧭 Default all users to the chat page after login
  return <Navigate to="/chat" replace />;
};

function App() {
  return (
    <BrowserRouter>
      <ClerkWithRouter>
        <Routes>

          {/* ================= PUBLIC PAGES ================= */}
          
          <Route path="/invite" element={<InvitePage />} />

          {/* ================= AUTH PAGES ================= */}

          {/* Sign In */}
          <Route
            path="/sign-in"
            element={
              <>
                <SignedIn>
                  <HomeRedirect />
                </SignedIn>
                <SignedOut>
                  <SignInPage />
                </SignedOut>
              </>
            }
          />

          {/* Sign Up */}
          <Route
            path="/sign-up"
            element={
              <>
                <SignedIn>
                  <HomeRedirect />
                </SignedIn>
                <SignedOut>
                  <SignUpPage />
                </SignedOut>
              </>
            }
          />

          <Route
            path="/forgot-password"
            element={
              <>
                <SignedIn>
                  <HomeRedirect />
                </SignedIn>
                <SignedOut>
                  <ForgotPasswordPage />
                </SignedOut>
              </>
            }
          />

          {/* ================= PROTECTED ================= */}

          <Route
            path="/chat"
            element={
              <ProtectedRoute>
                <ChatPage />
              </ProtectedRoute>
            }
          />

          {/* ================= ADMIN ================= */}
          
          <Route
            path="/admin"
            element={
              <RoleGuard allowedRoles={["admin"]}>
                <AdminDashboard />
              </RoleGuard>
            }
          />

          {/* ================= LAWYER ================= */}
          
          <Route
            path="/lawyer"
            element={
              <RoleGuard allowedRoles={["lawyer", "admin"]}>
                <LawyerDashboard />
              </RoleGuard>
            }
          />
          
          <Route
            path="/lawyer/tickets/:id"
            element={
              <RoleGuard allowedRoles={["lawyer", "admin"]}>
                <TicketDetailsPage />
              </RoleGuard>
            }
          />

          {/* ================= ROOT ================= */}

          <Route
            path="/"
            element={<HomeRedirect />}
          />

          {/* fallback */}
          <Route path="*" element={<Navigate to="/" replace />} />

        </Routes>
      </ClerkWithRouter>
    </BrowserRouter>
  );
}

export default App;

