import React, { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { initUserCounter, generateUserId } from "../../utils/userId";


const USERS = [
  { id: "u_1001", username: "admin1", password: "admin11" },
  { id: "u_1002", username: "admin2", password: "admin22" },
  { id: "u_1003", username: "admin3", password: "admin33" },
  { id: "u_1004", username: "admin4", password: "admin44" },
];

export default function SignInPage() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const navigate = useNavigate();

  // 🔑 init counter once
  useEffect(() => {
    initUserCounter();
  }, []);

  const handleLogin = () => {
    // 1️⃣ check default users
    const found = USERS.find(
      (u) => u.username === username && u.password === password
    );

    if (found) {
      localStorage.setItem("userId", found.id);
      localStorage.setItem("username", found.username);
      navigate("/chat");
      return;
    }

    // 2️⃣ new user
    const newUserId = generateUserId();
    localStorage.setItem("userId", newUserId);
    localStorage.setItem("username", username);

    navigate("/chat");
  };

  return (
    <div className="min-h-screen bg-black flex items-center justify-center">
      <div className="bg-[#111] p-10 rounded-2xl w-full max-w-md space-y-6">
        <h2 className="text-3xl font-bold text-white text-center">Login</h2>

        <input
          placeholder="Username"
          onChange={(e) => setUsername(e.target.value)}
          className="w-full p-3 rounded bg-[#1a1a1a] text-white"
        />

        <input
          type="password"
          placeholder="Password"
          onChange={(e) => setPassword(e.target.value)}
          className="w-full p-3 rounded bg-[#1a1a1a] text-white"
        />

        <button
          onClick={handleLogin}
          className="w-full bg-blue-600 text-white py-3 rounded"
        >
          Login
        </button>
      </div>
    </div>
  );
}
