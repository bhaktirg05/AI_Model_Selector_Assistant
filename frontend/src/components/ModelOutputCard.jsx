import React from "react";
import { CircularProgressbar, buildStyles } from "react-circular-progressbar";
import "react-circular-progressbar/dist/styles.css";

const ModelOutputCard = ({ modelData }) => {
  const {
    accuracy,
    rawMessage // full original message
  } = modelData;

  return (
    <div className="bg-white p-6 rounded-xl shadow-md w-full max-w-3xl mx-auto relative">
      {/* Full text message */}
      <div className="text-sm text-gray-800 whitespace-pre-wrap leading-relaxed">
        {rawMessage}
      </div>

      {/* Accuracy Chart (Top-Right corner) */}
      <div className="absolute top-4 right-4 w-16 h-16">
        <CircularProgressbar
          value={accuracy}
          text={`${accuracy}%`}
          styles={buildStyles({
            textColor: "#111",
            pathColor: "#4f46e5",
            trailColor: "#eee",
          })}
        />
        <p className="text-xs text-center text-gray-500 mt-1">Accuracy</p>
      </div>
    </div>
  );
};

export default ModelOutputCard;
