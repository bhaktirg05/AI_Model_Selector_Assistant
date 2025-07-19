import React, { useState, useEffect, useRef } from "react";
import axios from "axios";
import Sidebar from "./Sidebar";
import { Paperclip, Send } from "lucide-react";
import { useNavigate } from "react-router-dom"; // 👈 Add this at the top

const ChatWindow = ({ user, setUser }) => {
  const [message, setMessage] = useState("");
  const [chats, setChats] = useState([]);
  const [file, setFile] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [currentModel, setCurrentModel] = useState(null);
  const scrollRef = useRef(null);
  const navigate = useNavigate();

 // useEffect(() => {
  //  loadChatHistory();
//  }, [user]);

  const loadChatHistory = async () => {
    try {
      const res = await axios.get(`/history/${user}`);
      setChats(res.data);
    } catch (err) {
      console.error("Failed to load chat history:", err);
    }
  };

  const extractModelName = (responseText) => {
    // Simple logic: look for phrases like “I recommend”, “You should use”, etc.
    const patterns = [
      /i recommend ([\w\-\. ]+)/i,
      /you should use ([\w\-\. ]+)/i,
      /best model is ([\w\-\. ]+)/i,
      /i suggest ([\w\-\. ]+)/i,
    ];
    for (let pattern of patterns) {
      const match = responseText.match(pattern);
      if (match) return match[1].trim();
    }
    return null;
  };

  const handleSend = async (overrideMessage = null, isSystem = false) => {
    const finalMessage = overrideMessage || message;
    if (!finalMessage.trim()) return;

    const userMessage = { email: user, message: finalMessage };
    setChats((prev) => [...prev, userMessage]);
    setIsLoading(true);

    try {
      const res = await axios.post(`/chat`, {
        email: user,
        message: finalMessage,
      });

      const agentReply = res.data.response;

      const detectedModel = extractModelName(agentReply);
      if (detectedModel) {
        setCurrentModel(detectedModel);
      }

      const agentResponse = { username: "Agent", message: agentReply };
      setChats((prev) => [...prev, agentResponse]);
    } catch (error) {
      console.error("Error sending message:", error);
    }

    setMessage("");
    setIsLoading(false);
  };

  const handleUpload = async () => {
    if (!file) return;
    const formData = new FormData();
    formData.append("file", file);

    try {
      await axios.post(`/upload`, formData);
      alert("📁 File uploaded successfully!");
      setFile(null);
    } catch (error) {
      alert("Upload failed!");
    }
  };

  

// Inside your component
  const handleLogout = async () => {
    try {
      await axios.post("http://localhost:5000/logout", {
        email: user,
      });
      console.log("✅ User data cleared on logout.");
    } catch (error) {
      console.error("❌ Error during logout:", error);
    }

    // Clear local data and redirect to login
    setUser(null);
    localStorage.removeItem("email");
    navigate("/login");
  };



  const handleClear = () => {
    setChats([]);
    setCurrentModel(null);
  };

  const handleHistory = () => {
    loadChatHistory();
  };

  const handleSuggestAnotherModel = () => {
    handleSend("I don't like this model. Suggest another one.", true);
  };

  useEffect(() => {
    scrollRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chats]);

  useEffect(() => {
    const handleBeforeUnload = (e) => {
      const email = user;
      if (email) {
        const data = JSON.stringify({ email });
        const blob = new Blob([data], { type: 'application/json' });
        navigator.sendBeacon("http://localhost:5000/logout", blob);
        
        // Clear frontend state immediately
        setUser(null);
        localStorage.removeItem("email");
        
        console.log("🧹 User logged out via sendBeacon on tab close.");
      }
    };

    window.addEventListener("beforeunload", handleBeforeUnload);

    return () => {
      window.removeEventListener("beforeunload", handleBeforeUnload);
    };
  }, [user, setUser]); // Added setUser to dependencies

  return (
    <div className="flex flex-col h-screen bg-gradient-to-br from-pink-100 via-purple-100 to-indigo-200">
      <Sidebar onLogout={handleLogout} onClear={handleClear} onHistory={handleHistory} />

      <div className="flex-1 overflow-y-auto px-4 py-6">
        {currentModel && (
          <div className="text-center mb-4 text-sm text-gray-700">
            You're asking about: <strong>{currentModel}</strong>
            <button
              onClick={handleSuggestAnotherModel}
              className="ml-4 text-indigo-600 hover:underline text-xs"
            >
              Suggest Another Model
            </button>
          </div>
        )}

        {chats.map((chat, index) => (
          <div
            key={index}
            className={`flex ${chat.email === user ? "justify-end" : "justify-start"} mb-4`}
          >
            <div
              className={`px-4 py-3 rounded-2xl max-w-sm text-sm whitespace-pre-wrap shadow-md ${
                chat.email === user
                  ? "bg-blue-500 text-white rounded-br-none"
                  : "bg-white text-gray-800 rounded-bl-none"
              }`}
            >
              {chat.message}
            </div>
          </div>
        ))}

        {isLoading && (
          <div className="text-sm text-gray-400 italic text-center mb-2">Assistant is typing...</div>
        )}

        <div ref={scrollRef}></div>
      </div>

      <div className="sticky bottom-0 px-4 py-3 bg-white border-t shadow-lg flex items-center gap-2 z-10">
        <label className="cursor-pointer text-gray-600 hover:text-indigo-600">
          <Paperclip size={20} />
          <input type="file" className="hidden" onChange={(e) => setFile(e.target.files[0])} />
        </label>

        <input
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          className="flex-1 px-4 py-2 rounded-full border border-gray-300 focus:outline-none focus:ring-2 focus:ring-indigo-400 text-sm text-gray-800"
          placeholder="Type your message..."
        />

        <button
          onClick={() => handleSend()}
          disabled={!message.trim() || isLoading}
          className={`p-2 rounded-full shadow transition-transform hover:scale-105 ${
            !message.trim() || isLoading
              ? "bg-gray-300 text-white cursor-not-allowed"
              : "bg-indigo-500 hover:bg-indigo-600 text-white"
          }`}
        >
          <Send size={18} />
        </button>

        {file && (
          <button
            onClick={handleUpload}
            className="bg-green-500 hover:bg-green-600 text-white px-3 py-1 text-sm rounded-full"
          >
            Upload
          </button>
        )}
      </div>
    </div>
  );
};

export default ChatWindow;
