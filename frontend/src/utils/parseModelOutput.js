export function parseModelOutput(message) {
  if (!message.toLowerCase().includes("final best model recommended")) return null;

  const extract = (label) => {
    const regex = new RegExp(`${label}\\s*[:\\-]?\\s*(.+)`, "i");
    const match = message.match(regex);
    return match ? match[1].trim() : "";
  };

  const modelName = extract("Model Name");
  const price = extract("Price");
  const speed = extract("Speed");
  const cloud = extract("Cloud");
  const region = extract("Region");
  const reason = extract("Reason(?: for Selection)?");

  // More flexible accuracy match (with or without %)
  const accMatch = message.match(/Accuracy\s*[:\-]?\s*(\d+(\.\d+)?)(\s*%?)/i);
  const accuracy = accMatch ? parseFloat(accMatch[1]) : 0;

  return {
    modelName,
    price,
    speed,
    cloud,
    region,
    reason,
    accuracy,
    rawMessage: message,
  };
}
