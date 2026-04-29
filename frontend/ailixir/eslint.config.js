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
    ignores: ['src/components/atoms/**/*'],
    rules: {
      'no-restricted-imports': [
        'error',
        {
          patterns: [
            {
              group: ['@/components/atoms/*', '@src/components/atoms/*', '**/components/atoms/*'],
              message: 'Import atoms via the barrel: @/components/atoms',
            },
          ],
        },
      ],
    },
  },
]);
