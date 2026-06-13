import { serve } from "@hono/node-server";
import { Hono } from "hono";
// TODO: Implement firbase Auth token validation
import { initializeApp } from "firebase-admin/app";

const app = new Hono();

app.use(async (c, next) => {
  const authHeader = c.req.header("Authorization");
  if (authHeader && authHeader.startsWith("Bearer ")) {
    const token = authHeader.split(" ")[1];
    console.log("token:", token);
  } else {
    console.log("No Bearer Token found");
    return c.text("Unauthorized Request", 401);
  }

  next();
});

app.get("/scribe-token", (c) => {
  return c.json({ token: 1234 });
});

serve(
  {
    fetch: app.fetch,
    port: 3000,
  },
  (info) => {
    console.log(`Server is running on http://localhost:${info.port}`);
  },
);
