/**
 * Custom Clerk theme configuration for Digirett.
 * Since @clerk/themes is not installed, we provide a manual dark theme configuration.
 */

export const clerkDarkTheme = {
  variables: {
    colorBackground: '#0f0f0f',
    colorText: '#ffffff',
    colorPrimary: '#ffffff',
    colorTextOnPrimaryBackground: '#000000',
    colorTextSecondary: '#9ca3af',
    colorInputBackground: '#1a1a1a',
    colorInputText: '#ffffff',
    colorBorder: '#1f2937',
  },
  elements: {
    card: 'bg-[#0f0f0f] border border-gray-800',
    formButtonPrimary: 'bg-white text-black hover:bg-gray-200 transition-all',
    footerActionLink: 'text-white hover:text-gray-300 transition-all',
    formFieldInput: 'bg-[#1a1a1a] border-gray-800 text-white',
    dividerLine: 'bg-gray-800',
    dividerText: 'text-gray-500',
  }
};
