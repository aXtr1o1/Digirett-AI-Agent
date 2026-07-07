import { useEffect } from "react";

export default function useMobileViewport() {
  useEffect(() => {
    const handleResize = () => {
      // Calculate 1% of the actual window height
      const vh = window.innerHeight * 0.01;
      // Set the value in the --vh custom property on the root element
      document.documentElement.style.setProperty("--vh", `${vh}px`);
    };

    window.addEventListener("resize", handleResize);
    window.addEventListener("orientationchange", handleResize);
    handleResize();

    return () => {
      window.removeEventListener("resize", handleResize);
      window.removeEventListener("orientationchange", handleResize);
    };
  }, []);
}
