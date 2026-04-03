import dotenv from "dotenv";
dotenv.config();
console.log("👉 User command:", userText);

const response = await fetch(
  `https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent?key=${process.env.GEMINI_API_KEY}`,
  {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      contents: [{ parts: [{ text: prompt }] }]
    })
  }
);

console.log("👉 Response status:", response.status);

const data = await response.json();
console.log("👉 Gemini raw:", JSON.stringify(data, null, 2));
import fetch from "node-fetch";

export async function processCommand(userText) {
  const prompt = `You are a web navigation assistant. Convert the user's command into a JSON action.

Allowed actions:
- SCROLL_DOWN — user wants to scroll down
- SCROLL_UP — user wants to scroll up
- NAVIGATE — user wants to go to a specific website. Include "url" field.
- SEARCH — user wants to search for something. Include "query" field.
- CLICK — user wants to click something. Include "selector" field (CSS selector).

Rules:
- Return ONLY valid JSON, nothing else, no explanation, no markdown
- For NAVIGATE, always include a full URL starting with https://
- For SEARCH, include the search query as a string

Examples:
User: "scroll down" → {"action":"SCROLL_DOWN"}
User: "go to youtube" → {"action":"NAVIGATE","url":"https://www.youtube.com"}
User: "take me to MrBeast channel" → {"action":"NAVIGATE","url":"https://www.youtube.com/@MrBeast"}
User: "search cats on youtube" → {"action":"SEARCH","query":"cats site:youtube.com"}
User: "search python tutorials" → {"action":"SEARCH","query":"python tutorials"}
User: "go to trending" → {"action":"NAVIGATE","url":"https://www.youtube.com/feed/trending"}
User: "open google maps" → {"action":"NAVIGATE","url":"https://maps.google.com"}

Command: "${userText}"`;

  const response = await fetch(
    `https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent?key=${process.env.GEMINI_API_KEY}`,
    {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        contents: [{ parts: [{ text: prompt }] }]
      })
    }
  );

  if (!response.ok) {
    const err = await response.text();
    throw new Error(`Gemini API error ${response.status}: ${err}`);
  }

  const data = await response.json();
  const textOutput = data.candidates?.[0]?.content?.parts?.[0]?.text || "{}";

  // Remove markdown code fences if Gemini adds them
 let cleaned = textOutput
  .replace(/```json|```/g, "")
  .replace(/\n/g, "")
  .trim();

console.log("👉 Cleaned output:", cleaned);

  try {
    return JSON.parse(cleaned);
  } catch (err) {
  console.error("❌ JSON Parse Error:", cleaned);
  return { action: "UNKNOWN" };
}
}*/





