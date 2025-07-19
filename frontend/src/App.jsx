import React, { useState, useEffect } from "react";
import { BrowserRouter as Router, Routes, Route, Navigate } from "react-router-dom";

import Login from "./components/Login";
import Signup from "./components/Signup";
import ChatWindow from "./components/ChatWindow";

function App() {
  const [user, setUser] = useState(null);

  useEffect(() => {
    const savedEmail = localStorage.getItem("email");
    console.log("📦 Loaded from localStorage:", savedEmail); // Debug
    if (savedEmail) {
      setUser(savedEmail);
    }
  }, []);

  return (
    <Router>
      <Routes>
        <Route path="/" element={<Navigate to="/login" />} />
        <Route path="/login" element={<Login setUser={setUser} />} />
        <Route path="/signup" element={<Signup setUser={setUser} />} />
        <Route
          path="/chat"
          element={
            user ? (
              <ChatWindow user={user} setUser={setUser} />
            ) : (
              <Navigate to="/login" />
            )
          }
        />
      </Routes>
    </Router>
  );
}

export default App;
