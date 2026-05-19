import React from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { SignedIn, SignedOut } from "@clerk/clerk-react";
import SSOCallback from "./components/auth/SSOCallback";

import ClerkWithRouter from "./providers/ClerkWithRouter";
import ProtectedRoute from "./components/auth/ProtectedRoute";
import RoleGuard from "./components/auth/RoleGuard";

import SignInPage from "./pages/SignInPage";
import SignUpForm from "./components/auth/SignUpForm";
import ChatPage from "./pages/ChatPage";
import InvitePage from "./pages/InvitePage";
import AdminDashboard from "./pages/AdminDashboard";
import LawyerDashboard from "./pages/LawyerDashboard";
import TicketDetailsPage from "./pages/TicketDetailsPage";
import ForgotPasswordPage from "./pages/ForgotPasswordPage";
import ProvisioningPage from "./pages/ProvisioningPage";
import SuspendedPage from "./pages/SuspendedPage";
import { useUser, useAuth } from "@clerk/clerk-react";
import { ThemeProvider } from "./providers/ThemeProvider";

const HomeRedirect = () => {
  const { user, isLoaded: userLoaded } = useUser();
  const { isSignedIn, isLoaded: authLoaded } = useAuth();

  // 1. If not loaded, wait
  if (!authLoaded || !userLoaded) {
    return (
      <div className="min-h-screen bg-black flex flex-col items-center justify-center p-6 text-center">
        <div className="relative mb-8">
          <div className="absolute inset-0 bg-white/10 rounded-full animate-ping scale-150"></div>
          <div className="relative bg-[#0f0f0f] p-6 rounded-full border border-gray-800 shadow-2xl">
            <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-white"></div>
          </div>
        </div>

        <h2 className="text-2xl font-bold text-white mb-2 animate-pulse">
          Finalizing your workspace...
        </h2>
        <p className="text-gray-400 max-w-xs mx-auto">
          We're syncing your professional permissions and preparing your dashboard.
        </p>
      </div>
    );
  }

  // 2. If not signed in, always show sign-in page first
  if (!isSignedIn) {
    return <Navigate to="/sign-in" replace />;
  }

  // 2. Fresh session cleanup
  localStorage.removeItem("conversationId");

  // 3. Dynamic Redirect based on Role
  const role = user?.publicMetadata?.role || "user";
  console.log(`LOGIN_SUCCESS: Redirecting ${role} to home dashboard...`);

  if (role === "suspended") {
    return <Navigate to="/suspended" replace />;
  } else if (role === "admin") {
    return <Navigate to="/admin" replace />;
  } else if (role === "lawyer") {
    return <Navigate to="/lawyer" replace />;
  }

  return <Navigate to="/chat" replace />;
};

function App() {
  return (
    <ThemeProvider>
      <BrowserRouter>
        <ClerkWithRouter>
          <Routes>

            {/* ================= PUBLIC PAGES ================= */}

            <Route path="/invite" element={<InvitePage />} />
            <Route path="/provisioning" element={<ProvisioningPage />} />
            <Route path="/suspended" element={<SuspendedPage />} />
            <Route
              path="/sso-callback"
              element={<SSOCallback />}
            />

            {/* ================= AUTH PAGES ================= */}

            {/* Sign In */}
            <Route
              path="/sign-in/*"
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
              path="/sign-up/*"
              element={
                <>
                  <SignedIn>
                    <HomeRedirect />
                  </SignedIn>
                  <SignedOut>
                    <SignUpForm />
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

            <Route
              path="/chat/:id"
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
    </ThemeProvider>
  );
}

export default App;