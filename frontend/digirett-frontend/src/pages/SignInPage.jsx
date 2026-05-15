import { SignIn } from "@clerk/clerk-react";
import { clerkDarkTheme as dark } from "../styles/clerkTheme";
import SocialLogin from "../components/auth/SocialLogin";

const SignInPage = () => {
  return (
    <div className="min-h-screen bg-black flex items-center justify-center p-4 py-12">
      <div className="w-full max-w-[480px]">
        {/* Unified Card Container */}
        <div className="bg-[#0f0f0f] border border-gray-800 rounded-[32px] p-8 sm:p-10 shadow-2xl space-y-6 overflow-hidden">
          <div className="space-y-1.5 text-center">
            <h1 className="text-2xl font-bold text-white tracking-tight">Welcome back</h1>
            <p className="text-gray-500 text-xs">Please enter your details to sign in</p>
          </div>

          <SocialLogin />

          <div className="relative">
            <div className="absolute inset-0 flex items-center">
              <span className="w-full border-t border-gray-800/50"></span>
            </div>
            <div className="relative flex justify-center text-[10px] uppercase tracking-[0.2em]">
              <span className="bg-[#0f0f0f] px-4 text-gray-500 font-bold">Or continue with</span>
            </div>
          </div>

          <div className="w-full">
            <SignIn
              appearance={{
                baseTheme: dark,
                elements: {
                  rootBox: "w-full",
                  card: "bg-transparent border-none shadow-none p-0 m-0 w-full max-w-full",
                  main: "w-full m-0 p-0",
                  form: "w-full space-y-4",
                  socialButtonsBlockButton: "hidden",
                  dividerRow: "hidden",
                  formButtonPrimary: "bg-white text-black hover:bg-gray-100 font-bold py-3 w-full rounded-xl transition-all active:scale-[0.98] mt-2",
                  formFieldInput: "bg-[#1a1a1a] border-gray-800 text-white focus:border-white rounded-xl h-11 transition-all px-4 w-full",
                  formFieldLabel: "text-gray-400 font-medium text-xs mb-1",
                  footer: "bg-transparent mt-4 w-full",
                  footerActionLink: "text-white font-bold hover:text-gray-300 transition-colors",
                  identityPreviewText: "text-gray-300",
                  identityPreviewEditButton: "text-white hover:text-gray-300",
                }
              }}
              routing="path"
              path="/sign-in"
              signUpUrl="/sign-up"
              fallbackRedirectUrl="/"
            />
          </div>
        </div>
      </div>
    </div>
  );
};

export default SignInPage;
