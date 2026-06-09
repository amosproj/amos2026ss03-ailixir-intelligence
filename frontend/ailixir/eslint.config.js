// https://docs.expo.dev/guides/using-eslint/
const { defineConfig } = require('eslint/config');
const expoConfig = require('eslint-config-expo/flat');
const eslintPluginPrettierRecommended = require('eslint-plugin-prettier/recommended');

module.exports = defineConfig([
  expoConfig,
  eslintPluginPrettierRecommended,
  {
    ignores: ['dist/*'],
  },
  {
    files: ['src/**/*.{ts,tsx,js,jsx}'],
    ignores: ['src/components/atoms/**/*', 'src/components/molecules/**/*', 'src/components/organisms/**/*'],
    rules: {
      'no-restricted-imports': [
        'error',
        {
          patterns: [
            {
              group: ['@/components/atoms/*', '@src/components/atoms/*', '**/components/atoms/*'],
              message: 'Import atoms via the barrel: @/components/atoms',
            },
            {
              group: ['@/components/molecules/*', '@src/components/molecules/*', '**/components/molecules/*'],
              message: 'Import molecules via the barrel: @/components/molecules',
            },
            {
              group: ['@/components/organisms/*', '@src/components/organisms/*', '**/components/organisms/*'],
              message: 'Import organisms via the barrel: @/components/organisms',
            },
          ],
        },
      ],
    },
  },
]);
