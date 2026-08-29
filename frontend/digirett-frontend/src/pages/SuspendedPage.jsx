import React from "react";
import { useClerk } from "@clerk/clerk-react";
import { AlertCircle, LogOut, Mail } from "lucide-react";

const SuspendedPage = () => {
  const { signOut } = useClerk();

  const handleLogout = async () => {
    await signOut();
    window.location.href = "/sign-in";
  };

  return (
    <div className="min-h-screen bg-slate-50 flex items-center justify-center p-4">
      <div className="max-w-md w-full bg-white rounded-3xl shadow-2xl shadow-slate-200/50 border border-slate-100 p-8 text-center">
        <div className="w-20 h-20 bg-red-50 rounded-2xl flex items-center justify-center mx-auto mb-6">
          <AlertCircle className="w-10 h-10 text-red-500" />
        </div>
        
        <h1 className="text-2xl font-black text-slate-900 mb-2 tracking-tight">
          Account Suspended
        </h1>
        
        <p className="text-slate-500 text-sm leading-relaxed mb-8">
          Your access to Digirett has been restricted by an administrator. 
          If you believe this is a mistake, please contact our support team.
        </p>

        <div className="space-y-3">
          <a 
            href="mailto:support@digirett.com"
            className="flex items-center justify-center gap-2 w-full py-3.5 bg-indigo-600 text-white rounded-xl font-bold text-sm hover:bg-indigo-700 transition-all shadow-lg shadow-indigo-200"
          >
            <Mail size={18} />
            Contact Support
          </a>
          
          <button 
            onClick={handleLogout}
            className="flex items-center justify-center gap-2 w-full py-3.5 bg-white text-slate-600 border border-slate-200 rounded-xl font-bold text-sm hover:bg-slate-50 transition-all"
          >
            <LogOut size={18} />
            Sign Out
          </button>
        </div>

        <div className="mt-8 pt-6 border-t border-slate-100">
          <p className="text-[10px] text-slate-400 font-bold uppercase tracking-widest">
            Digirett Legal AI • Restricted Access
          </p>
        </div>
      </div>
    </div>
  );
};

export default SuspendedPage;
