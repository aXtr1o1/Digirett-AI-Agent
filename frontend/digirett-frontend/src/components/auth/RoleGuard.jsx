import React from "react";
import { useUser } from "@clerk/clerk-react";
import { Navigate } from "react-router-dom";

/**
 * RoleGuard component to protect routes based on Clerk publicMetadata.role
 * 
 * @param {Array} allowedRoles - List of roles that can access the route
 * @param {React.ReactNode} children - The protected component
 * @param {string} redirectTo - Where to redirect if unauthorized (default: "/")
 */
const RoleGuard = ({ allowedRoles, children, redirectTo = "/" }) => {
  const { user, isLoaded, isSignedIn } = useUser();

  if (!isLoaded) {
    return (
      <div className="flex items-center justify-center h-screen bg-gray-50">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600"></div>
      </div>
    );
  }

  if (!isSignedIn) {
    return <Navigate to="/sign-in" replace />;
  }

  const userRole = user?.publicMetadata?.role || "user";

  if (!allowedRoles.includes(userRole)) {
    console.warn(`[RoleGuard] Access denied for role: ${userRole}. Allowed: ${allowedRoles}`);
    return <Navigate to={redirectTo} replace />;
  }

  return children;
};

export default RoleGuard;
