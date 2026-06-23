import { ElevenLabsClient } from "@elevenlabs/elevenlabs-js";
import { defineSecret, defineString } from "firebase-functions/params";
import { onInit } from "firebase-functions/v2/core";

export const elevenlabsApiKey = defineSecret("ELEVENLABS_API_KEY");
export const agentId = defineString("ELEVENLABS_AGENT_ID");

let elevenlabs: ElevenLabsClient;

onInit(() => {
  elevenlabs = new ElevenLabsClient({ apiKey: elevenlabsApiKey.value() });
});

export const getSignedUrl = async () => {
  try {
    const response =
      await elevenlabs.conversationalAi.conversations.getSignedUrl({
        agentId: agentId.value(),
      });
    return response.signedUrl;
  } catch (error) {
    console.error("Error getting signed URL:", error);
    throw error;
  }
};
