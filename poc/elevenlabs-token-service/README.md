# Elevenlabs Token Provider

> **Proof of concept — not part of the deployed system.** This lives under
> `poc/` and prototypes ElevenLabs token issuance. The production equivalent is
> the Firebase Cloud Function in
> [`functions/src/utils/elevenlabs-token-service.ts`](../../functions/src/utils/elevenlabs-token-service.ts).
> Voice chat overall is future work — groundwork in place, not active yet. See
> the root [README](../../README.md#future-work).

## About

This service answers incoming requests to the `/scribe-token`.
It issues a token that is valid for 15 Minutes.

## How to run 

```
npm install
npm run dev
```

```
open http://localhost:3000/scribe-token
```
