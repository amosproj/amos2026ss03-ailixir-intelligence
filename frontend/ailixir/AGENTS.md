# Commands

- Install deps: `npm install`.
- Dev server: `npm run start`.
- Platform targets: `npm run ios`, `npm run android`, `npm run web`
- Lint: `npm run lint`
- Typecheck: `npx tsc --noEmit` from `frontend/ailixir` (there is no `typecheck` script)
- Use `npx expo install <package name>` for the installation of new packages.
- There is currently no test script, build script, CI workflow, or pre-commit config in the repo.

# App Structure

- Path alias `@/*` maps to `./src/*`.

# Conventions

- Always import Components from their corresponding barrel files `@/components/atoms`, `@/components/molecules`, `@/components/organisms`
- Custom components are prefixed with a `C`, e.g. `CButton`or `CInput`. Always prefer using these instead of the raw tamagui components.
- Do not hand-edit `./expo-env.d.ts`; it is Expo-generated even though it is currently tracked.
- Assume that a dev server is already running.

# Code style

- read .prettierrc.yaml for style conventions.

# assistant-ui
This project uses assistant-ui for chat interfaces.
Documentation: https://www.assistant-ui.com/llms-full.txt
Key patterns:
- Use AssistantRuntimeProvider at the app root
- Thread component for full chat interface
- AssistantModal for floating chat widget
- useChatRuntime hook with AI SDK transport
