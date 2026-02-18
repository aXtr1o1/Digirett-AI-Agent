import { useEffect } from 'react';
import { useSignIn } from '@clerk/clerk-react';

const SSOCallback = () => {
  const { isLoaded } = useSignIn();

  useEffect(() => {
    if (!isLoaded) return;
    // Clerk automatically finalizes OAuth here
  }, [isLoaded]);

  return <p>Signing you in…</p>;
};

export default SSOCallback;
