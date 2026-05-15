import { createV5Theme, defaultChildrenThemes } from '@tamagui/config/v5';
import { v5ComponentThemes } from '@tamagui/themes/v5';
import { yellow, yellowDark, red, redDark, green, greenDark } from '@tamagui/colors';

const darkPalette = [
  'hsla(310, 16%, 1%, 1)',
  'hsla(310, 16%, 6%, 1)',
  'hsla(310, 16%, 12%, 1)',
  'hsla(310, 16%, 17%, 1)',
  'hsla(310, 16%, 23%, 1)',
  'hsla(310, 16%, 28%, 1)',
  'hsla(310, 16%, 34%, 1)',
  'hsla(310, 16%, 39%, 1)',
  'hsla(310, 16%, 45%, 1)',
  'hsla(310, 16%, 50%, 1)',
  'hsla(0, 15%, 93%, 1)',
  'hsla(0, 15%, 99%, 1)',
];
const lightPalette = [
  'hsla(310, 16%, 94%, 1)',
  'hsla(310, 16%, 89%, 1)',
  'hsla(310, 16%, 84%, 1)',
  'hsla(310, 16%, 79%, 1)',
  'hsla(310, 16%, 74%, 1)',
  'hsla(310, 16%, 70%, 1)',
  'hsla(310, 16%, 65%, 1)',
  'hsla(310, 16%, 60%, 1)',
  'hsla(310, 16%, 55%, 1)',
  'hsla(310, 16%, 50%, 1)',
  'hsla(0, 15%, 15%, 1)',
  'hsla(0, 15%, 1%, 1)',
];

// custom accent colors
const accentLight = {
  accent1: 'hsla(250, 50%, 40%, 1)',
  accent2: 'hsla(250, 50%, 43%, 1)',
  accent3: 'hsla(250, 50%, 46%, 1)',
  accent4: 'hsla(250, 50%, 48%, 1)',
  accent5: 'hsla(250, 50%, 51%, 1)',
  accent6: 'hsla(250, 50%, 54%, 1)',
  accent7: 'hsla(250, 50%, 57%, 1)',
  accent8: 'hsla(250, 50%, 59%, 1)',
  accent9: 'hsla(250, 50%, 62%, 1)',
  accent10: 'hsla(250, 50%, 65%, 1)',
  accent11: 'hsla(250, 50%, 95%, 1)',
  accent12: 'hsla(250, 50%, 95%, 1)',
};

const accentDark = {
  accent1: 'hsla(250, 50%, 35%, 1)',
  accent2: 'hsla(250, 50%, 38%, 1)',
  accent3: 'hsla(250, 50%, 41%, 1)',
  accent4: 'hsla(250, 50%, 43%, 1)',
  accent5: 'hsla(250, 50%, 46%, 1)',
  accent6: 'hsla(250, 50%, 49%, 1)',
  accent7: 'hsla(250, 50%, 52%, 1)',
  accent8: 'hsla(250, 50%, 54%, 1)',
  accent9: 'hsla(250, 50%, 57%, 1)',
  accent10: 'hsla(250, 50%, 60%, 1)',
  accent11: 'hsla(250, 50%, 90%, 1)',
  accent12: 'hsla(250, 50%, 95%, 1)',
};

// Custom background colors for light and dark themes
const backgroundLight = {
  background: '#FFFFFF',
};

const backgroundDark = {
  background: '#1a1a1a',
};

const builtThemes = createV5Theme({
  darkPalette,
  lightPalette,
  componentThemes: v5ComponentThemes,
  accent: {
    light: accentLight,
    dark: accentDark,
  },
  childrenThemes: {
    // Include default color themes (blue, red, green, yellow, etc.)
    ...defaultChildrenThemes,

    // Semantic color themes for warnings, errors, and success states
    warning: {
      light: yellow,
      dark: yellowDark,
    },
    error: {
      light: red,
      dark: redDark,
    },
    success: {
      light: green,
      dark: greenDark,
    },

    // Custom background theme
    background: {
      light: backgroundLight,
      dark: backgroundDark,
    },
  },
});

export type Themes = typeof builtThemes;

// the process.env conditional here is optional but saves web client-side bundle
// size by leaving out themes JS. tamagui automatically hydrates themes from CSS
// back into JS for you, and the bundler plugins set TAMAGUI_ENVIRONMENT. so
// long as you are using the Vite, Next, Webpack plugins this should just work,
// but if not you can just export builtThemes directly as themes:
export const themes: Themes = process.env.TAMAGUI_ENVIRONMENT === 'client' && process.env.NODE_ENV === 'production' ? ({} as any) : (builtThemes as any);
