import { useState, useCallback } from 'react';

/**
 * Custom hook for copying text to clipboard
 */
const useCopyToClipboard = () => {
  const [isCopied, setIsCopied] = useState(false);

  const copyToClipboard = useCallback(async (text) => {
    try {
      await navigator.clipboard.writeText(text);
      setIsCopied(true);

      // Reset after 2 seconds
      setTimeout(() => {
        setIsCopied(false);
      }, 2000);

      return true;
    } catch (err) {
      console.error('Failed to copy text:', err);
      setIsCopied(false);
      return false;
    }
  }, []);

  return { isCopied, copyToClipboard };
};

export default useCopyToClipboard;
