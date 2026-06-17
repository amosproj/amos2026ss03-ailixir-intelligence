import { serve } from "@hono/node-server";
import { Hono } from "hono";
import { cors } from "hono/cors";
import { ElevenLabsClient } from "@elevenlabs/elevenlabs-js";
import { loadEnvFile } from "node:process";
// TODO: Implement firbase Auth token validation
import { initializeApp } from "firebase-admin/app";

// initialization
loadEnvFile();
const app = new Hono();
const elevenlabs = new ElevenLabsClient({
  apiKey: process.env.ELEVENLABS_API_KEY,
});

// middleware
app.use('*', cors());
app.use(async (c, next) => {
  // TODO: implement authentication w/ firebase
  /*
  const authHeader = c.req.header("Authorization");
  if (authHeader && authHeader.startsWith("Bearer ")) {
    const token = authHeader.split(" ")[1];
    console.log("token:", token);
  } else {
    console.log("No Bearer Token found");
    return c.text("Unauthorized Request", 401);
  }
  */

  await next();
});
// endpoints
app.get("/scribe-token", async (c) => {
  const token = await elevenlabs.tokens.singleUse.create("realtime_scribe");
  return c.json(token);
});

// server
serve(
  {
    fetch: app.fetch,
    port: 3000,
  },
  (info) => {
    console.log(`Server is running on http://localhost:${info.port}`);
  },
);
