# AIlixir Intelligence — Frontend

## Prerequisites

- Node.js (v18+)
- [Xcode](https://developer.apple.com/xcode/) (iOS) or [Android Studio](https://developer.android.com/studio) (Android)

## Getting Started

```bash
git clone git@github.com:amosproj/amos2026ss03-ailixir-intelligence.git
cd frontend/ailixir
npm install
npm run ios   # or npm run android
npx expo start
```

## Project Structure

```
src/
├── app/            # Expo Router file-based routes
│   ├── (auth)/     # Authentication screens
│   └── (private)/  # Authenticated screens
├── components/     # UI components (Atomic Design)
├── constants/      # Design tokens, colors, spacing
├── data/           # Static data and fixtures
├── hooks/          # Custom React hooks
├── interfaces/     # TypeScript type definitions
├── lib/            # Shared utilities and helpers
├── runtimes/       # assistant-ui runtime setup
├── state/          # Jotai atoms and global state
├── static/         # Static assets
└── tamagui/        # Tamagui theme and config
```

### Atomic Design

Components follow Atomic Design principles, organized into three layers:

- **`atoms/`** — Smallest building blocks: buttons, inputs, icons, typography, badges.
- **`molecules/`** — Combinations of atoms: form fields, search bars, cards.
- **`organisms/`** — Complex UI sections: navigation bars, chat threads, document viewers.

Always import components from their corresponding barrel files:

```typescript
import { CButton } from "@/components/atoms";
import { CSearchBar } from "@/components/molecules";
import { ChatThread } from "@/components/organisms";
```

Custom components are prefixed with `C` (e.g. `CButton`, `CInput`), and should be preferred over raw Tamagui primitives.

## Commands

| Command | Description |
|---|---|
| `npm run ios` | Build and run on iOS simulator |
| `npm run android` | Build and run on Android emulator |
| `npm run lint` | Run ESLint |
| `npx tsc --noEmit` | Type-check the project |

## Key Libraries

- **[Tamagui](https://tamagui.dev/)** — Cross-platform UI and theming
- **[assistant-ui](https://www.assistant-ui.com/)** — Chat interface primitives
- **[TanStack Query](https://tanstack.com/query)** — Server state and async data
- **[Jotai](https://jotai.org/)** — Atomic state management
- **[Firebase](https://firebase.google.com/)** — Authentication and backend communication
- **[ElevenLabs](https://elevenlabs.io/)** — Voice chat integration
