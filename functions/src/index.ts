import { setGlobalOptions } from "firebase-functions";
import { onCall, HttpsError } from "firebase-functions/v2/https";
import { initializeApp } from "firebase-admin/app";

import {
  elevenlabsApiKey,
  getSignedUrl,
  getConversationToken,
} from "./utils/elevenlabs-token-service";

setGlobalOptions({ maxInstances: 2 });
initializeApp();

export const getSignedUrlFn = onCall(
  { secrets: [elevenlabsApiKey] },
  async (request) => {
    if (!request.auth) {
      throw new HttpsError("unauthenticated", "User must be authenticated");
    }

    try {
      const signedUrl = await getSignedUrl();
      return { signedUrl };
    } catch (error) {
      throw new HttpsError("internal", "Failed to get signed URL");
    }
  },
);

export const getWebrtcToken = onCall(
  { secrets: [elevenlabsApiKey] },
  async (request) => {
    if (!request.auth) {
      throw new HttpsError("unauthenticated", "User must be authenticated");
    }

    try {
      const token = await getConversationToken();
      return { token };
    } catch (error) {
      throw new HttpsError("internal", "Failed to get conversation token");
    }
  },
);
