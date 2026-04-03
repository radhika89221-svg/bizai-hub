import express from "express";
import cors from "cors";
import dotenv from "dotenv";
import routes from "./route.js";

dotenv.config();

// Fail fast if the API key is missing
if (!process.env.GEMINI_API_KEY) {
  throw new Error("Missing GEMINI_API_KEY in .env");
}

const app = express();

// Restrict CORS to your frontend origin in production
app.use(cors({
  origin: ["http://localhost:5500", "http://127.0.0.1:5500"]
}));

app.use(express.json());
app.use("/", routes);

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
  console.log(`Server running on http://localhost:${PORT}`);
});
processCommand("scroll down").then(console.log);