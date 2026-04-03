export const addMessage = (type, text) => {
  const chatBox = document.getElementById("chatBox");

  const div = document.createElement("div");
  div.className = `message ${type}`; // fixed: was split across two lines
  div.innerText = text;

  chatBox.appendChild(div);
  chatBox.scrollTop = chatBox.scrollHeight;
};