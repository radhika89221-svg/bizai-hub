export const speak = (text, lang = "en-US") => {
  const msg = new SpeechSynthesisUtterance(text);
  msg.lang = lang;
  speechSynthesis.speak(msg);
}; // fixed: missing closing brace