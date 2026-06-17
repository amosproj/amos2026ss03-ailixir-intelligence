import { setGlobalOptions } from "firebase-functions";
import { onRequest } from "firebase-functions/https";
import { initializeApp } from "firebase-admin/app";
import { getAuth } from "firebase-admin/auth";
import * as logger from "firebase-functions/logger";

setGlobalOptions({ maxInstances: 2 });
initializeApp();

export const sessionToken = onRequest(async (request, response) => {
  const authHeader = request.headers.authorization;

  if (!authHeader || !authHeader.toLowerCase().startsWith("bearer ")) {
    logger.warn("sessionToken: missing authorization header");
    response.status(401).send("Token missing");
    return;
  }

  try {
    const token = authHeader.slice(7);
    const decodedToken = await getAuth().verifyIdToken(token);
    logger.info("sessionToken: token verified", {
      uid: decodedToken.uid,
      email: decodedToken.email,
    });
    response.json({ token: 123 });
  } catch (error) {
    logger.error("sessionToken: token verification failed", error);
    response.status(401).send("Token invalid");
  }
});
