import React from "react";
import UserProfile from "../auth/UserProfile";

const Header = () => {
  return (
    <header className="relative h-14 border-b border-gray-900 bg-black flex items-center text-white">


      {/* Right side profile */}
      <div className="ml-auto pr-6">
        <UserProfile />
      </div>

    </header>
  );
};

export default Header;
