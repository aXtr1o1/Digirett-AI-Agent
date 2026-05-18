import { useAuth, useUser } from '@clerk/clerk-react';
import { Navigate } from 'react-router-dom';

const ProtectedRoute = ({ children }) => {
  const { isLoaded: authLoaded, isSignedIn } = useAuth();
  const { isLoaded: userLoaded } = useUser();

  if (!authLoaded || !userLoaded) {
    return (
      <div className="flex items-center justify-center h-screen bg-black">
        <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-white"></div>
      </div>
    );
  }

  if (!isSignedIn) {
    return <Navigate to="/sign-in" replace />;
  }

  return children;
};

export default ProtectedRoute;
