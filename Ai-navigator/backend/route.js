import express from "express";
import { processCommand } from "./gemini.js";

const router = express.Router();

router.post("/process-command", async (req, res) => {
  try {
    
    const { text } = req.body;

    if (!text) {
      return res.status(400).json({ error: "No text provided" });
    }

    // Cap input length to prevent abuse / prompt injection
    const sanitized = text.trim().slice(0, 500);

    const result = await processCommand(sanitized);
    res.json(result);
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: "Server error" });
  }
});

export default router;