// import { SignedIn, SignedOut } from '@clerk/clerk-react';
// import { Navigate } from 'react-router-dom';

// const ProtectedRoute = ({ children }) => {
//   return (
//     <>
//       <SignedIn>{children}</SignedIn>
//       <SignedOut>
//         <Navigate to="/sign-in" replace />
//       </SignedOut>
//     </>
//   );
// };

// export default ProtectedRoute;
import { Navigate } from "react-router-dom";

export default function ProtectedRoute({ children }) {
  const userId = localStorage.getItem("userId");

  if (!userId) {
    return <Navigate to="/sign-in" replace />;
  }

  return children;
}

