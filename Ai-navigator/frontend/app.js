import { addMessage } from "./ui.js";
import { speak } from "./voice.js";
import { getWebsiteOverview } from "./overview.js";

const statusEl = document.getElementById("status");

// ─── Helper: send command to your backend ───────────────────────────────────
async function sendCommand(text) {
  const response = await fetch("http://localhost:3000/process-command", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text })
  });
  return await response.json();
}

// ─── Helper: execute the action Gemini returns ──────────────────────────────
function executeAction(result, mode, lang) {
  const iframe = document.getElementById("siteFrame");
  const action = result.action;

  if (action === "SCROLL_DOWN") {
    iframe.contentWindow.scrollBy({ top: 400, behavior: "smooth" });
    addMessage("bot", "✅ Scrolling down...");

  } else if (action === "SCROLL_UP") {
    iframe.contentWindow.scrollBy({ top: -400, behavior: "smooth" });
    addMessage("bot", "✅ Scrolling up...");

  } else if (action === "NAVIGATE" && result.url) {
    iframe.src = result.url;
    addMessage("bot", `✅ Navigating to: ${result.url}`);
    if (mode === "voice") speak(`Navigating to ${result.url}`, lang);

  } else if (action === "SEARCH" && result.query) {
    const searchUrl = `https://www.google.com/search?q=${encodeURIComponent(result.query)}`;
    iframe.src = searchUrl;
    addMessage("bot", `✅ Searching for: ${result.query}`);
    if (mode === "voice") speak(`Searching for ${result.query}`, lang);

  } else if (action === "CLICK" && result.selector) {
    try {
      const el = iframe.contentDocument.querySelector(result.selector);
      if (el) {
        el.click();
        addMessage("bot", `✅ Clicked: ${result.selector}`);
      } else {
        addMessage("bot", `⚠️ Could not find element to click.`);
      }
    } catch {
      addMessage("bot", "⚠️ This site blocks outside control. Try searching instead.");
    }

  } else {
    addMessage("bot", `⚠️ Got action: "${action}" — try saying 'scroll down', 'search cats on YouTube', or 'go to google.com'`);
  }
}

// ─── Mic listening ──────────────────────────────────────────────────────────
function startListening(lang = "en-US") {
  return new Promise((resolve, reject) => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      alert("Please use Chrome or Edge for voice commands.");
      return;
    }
    const recognition = new SpeechRecognition();
    recognition.lang = lang;
    recognition.onresult = (e) => resolve(e.results[0][0].transcript);
    recognition.onerror = (e) => reject(e);
    recognition.start();
  });
}

// ─── Process any command ────────────────────────────────────────────────────
async function processUserCommand(text) {
  const mode = document.getElementById("mode").value;
  const lang = document.getElementById("language").value;

  addMessage("user", text);
  statusEl.textContent = "⏳ Thinking...";

  try {
    const result = await sendCommand(text);
    statusEl.textContent = "";
    executeAction(result, mode, lang);
  } catch (err) {
    statusEl.textContent = "";
    addMessage("bot", "❌ Server error. Is your backend running on port 3000?");
    console.error(err);
  }
}

// ─── START BUTTON ───────────────────────────────────────────────────────────
document.getElementById("startBtn").onclick = () => {
  const url = document.getElementById("urlInput").value.trim();
  const mode = document.getElementById("mode").value;
  const lang = document.getElementById("language").value;

  if (!url) return alert("Please enter a URL first.");

  const finalUrl = url.startsWith("http") ? url : "https://" + url;

  document.getElementById("siteFrame").src = finalUrl;

  const overview = getWebsiteOverview(finalUrl);
  addMessage("bot", `✅ Loaded: ${finalUrl}\n${overview}`);
  addMessage("bot", `🎤 Try saying: "scroll down", "search cats", "go to trending"`);

  if (mode === "voice") speak(overview, lang);
};

// ─── MIC BUTTON ─────────────────────────────────────────────────────────────
document.getElementById("micBtn").onclick = async () => {
  const lang = document.getElementById("language").value;
  statusEl.textContent = "🎤 Listening...";
  try {
    const text = await startListening(lang);
    statusEl.textContent = "";
    await processUserCommand(text);
  } catch (err) {
    statusEl.textContent = "";
    addMessage("bot", "❌ Mic error — allow microphone access in your browser.");
    console.error(err);
  }
};

// ─── SEND BUTTON ────────────────────────────────────────────────────────────
document.getElementById("sendBtn").onclick = async () => {
  const text = document.getElementById("textInput").value.trim();
  if (!text) return;
  document.getElementById("textInput").value = "";
  await processUserCommand(text);
};

// Press Enter to send
document.getElementById("textInput").addEventListener("keydown", async (e) => {
  if (e.key === "Enter") {
    const text = e.target.value.trim();
    if (!text) return;
    e.target.value = "";
    await processUserCommand(text);
  }
});