import React from "react";
import { FaHistory } from "react-icons/fa"; // history icon

const Sidebar = ({ onLogout, onClear, onHistory }) => {
  return (
    <div className="flex justify-between items-center p-4 bg-gray-900 text-white text-sm border-b border-gray-700">
      <div className="flex gap-4">
        <button onClick={onClear} className="hover:underline">Clear Chat</button>
        <button onClick={onHistory} title="Load Chat History" className="hover:text-blue-400 flex items-center gap-1">
          <FaHistory size={14} />
          History
        </button>
      </div>
      <button onClick={onLogout} className="hover:underline">Logout</button>
    </div>
  );
};

export default Sidebar;
