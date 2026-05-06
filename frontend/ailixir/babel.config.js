module.exports = function (api) {
  api.cache(true);

  return {
    presets: ['babel-preset-expo'],
    plugins: [
      [
        '@tamagui/babel-plugin',
        {
          config: './src/tamagui.config.ts',
          components: ['tamagui'],
          logTimings: false,
        },
      ],
      'react-native-reanimated/plugin',
    ],
  };
};
