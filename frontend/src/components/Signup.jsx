import React, { useState } from "react";
import { useNavigate, Link } from "react-router-dom";

const Signup = () => {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const navigate = useNavigate();

  const handleSignup = async () => {
    if (!name.trim() || !email.trim() || !password.trim()) {
      setError("All fields are required.");
      return;
    }

    try {
      const res = await fetch("http://localhost:5000/signup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: name.trim(),
          email: email.trim(),
          password: password.trim(),
        }),
      });

      const data = await res.json();

      if (data.status === "success") {
        navigate("/login");
      } else {
        setError(data.message || "Signup failed");
      }
    } catch (err) {
      console.error("Signup error:", err);
      setError("Server error. Please try again.");
    }
  };

  return (
    <div className="h-screen w-full flex items-center justify-center bg-gradient-to-br from-yellow-100 via-pink-100 to-purple-200">
      <div className="bg-white/90 p-10 rounded-3xl shadow-xl border border-gray-200 w-[90%] max-w-md backdrop-blur-md">
        <h2 className="text-3xl font-semibold text-gray-800 mb-6 text-center tracking-wide">
          Create Your Account 🌸
        </h2>

        {error && (
          <p className="text-red-600 bg-red-100 px-4 py-2 rounded-md mb-4 text-sm text-center shadow">
            {error}
          </p>
        )}

        <input
          type="text"
          placeholder="Full Name"
          className="w-full p-3 mb-4 rounded-xl bg-white border border-gray-300 placeholder-gray-500 text-gray-800 shadow-sm focus:outline-none focus:ring-2 focus:ring-pink-400 transition-all"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />

        <input
          type="email"
          placeholder="Email"
          className="w-full p-3 mb-4 rounded-xl bg-white border border-gray-300 placeholder-gray-500 text-gray-800 shadow-sm focus:outline-none focus:ring-2 focus:ring-pink-400 transition-all"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />

        <input
          type="password"
          placeholder="Password"
          className="w-full p-3 mb-6 rounded-xl bg-white border border-gray-300 placeholder-gray-500 text-gray-800 shadow-sm focus:outline-none focus:ring-2 focus:ring-pink-400 transition-all"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />

        <button
          onClick={handleSignup}
          className="w-full bg-gradient-to-r from-pink-400 to-purple-400 hover:from-pink-500 hover:to-purple-500 text-white py-3 rounded-xl font-medium shadow-md transition-transform hover:scale-105"
        >
          Sign Up
        </button>

        <div className="text-center mt-6 text-sm text-gray-600">
          Already have an account?{" "}
          <Link to="/login" className="text-pink-500 hover:underline font-medium">
            Go to Login
          </Link>
        </div>
      </div>
    </div>
  );
};

export default Signup;
