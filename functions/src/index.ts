import { setGlobalOptions } from "firebase-functions";
import { onRequest } from "firebase-functions/https";
import { initializeApp } from "firebase-admin/app";
import { getAuth } from "firebase-admin/auth";
import * as logger from "firebase-functions/logger";

import {
  elevenlabsApiKey,
  getSignedUrl,
} from "./utils/elevenlabs-token-service";

setGlobalOptions({ maxInstances: 2 });
initializeApp();

export const signedUrl = onRequest(
  { secrets: [elevenlabsApiKey] },
  async (request, response) => {
    const authHeader = request.headers.authorization;

    if (!authHeader || !authHeader.toLowerCase().startsWith("bearer ")) {
      logger.warn("elevenlabsConversationUrl: missing authorization header");
      response.status(401).send("Unauthorized");
      return;
    }

    try {
      const token = authHeader.slice(7);
      const decodedToken = await getAuth().verifyIdToken(token);
      logger.info("elevenlabsConversationUrl: token verified", {
        uid: decodedToken.uid,
        email: decodedToken.email,
      });

      const signedUrl = await getSignedUrl();
      response.json({ signedUrl });
    } catch (error) {
      logger.error("elevenlabsConversationUrl: request failed", error);
      response.status(401).send("Unauthorized");
    }
  },
);
