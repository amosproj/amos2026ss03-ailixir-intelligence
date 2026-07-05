import { CText } from '@/components/atoms';
import React, { useEffect, useRef } from 'react';
import { Animated, Easing, View } from 'react-native';
import { useTheme } from 'tamagui';

export const ThinkingIndicator: React.FC = () => {
  const theme = useTheme();
  const dot1 = useRef(new Animated.Value(0.35)).current;
  const dot2 = useRef(new Animated.Value(0.35)).current;
  const dot3 = useRef(new Animated.Value(0.35)).current;

  useEffect(() => {
    const createDotAnimation = (value: Animated.Value, delay: number) =>
      Animated.loop(
        Animated.sequence([
          Animated.delay(delay),
          Animated.timing(value, {
            toValue: 1,
            duration: 280,
            easing: Easing.inOut(Easing.ease),
            useNativeDriver: true,
          }),
          Animated.timing(value, {
            toValue: 0.35,
            duration: 280,
            easing: Easing.inOut(Easing.ease),
            useNativeDriver: true,
          }),
        ]),
      );

    const animations = [createDotAnimation(dot1, 0), createDotAnimation(dot2, 140), createDotAnimation(dot3, 280)];
    animations.forEach((animation) => animation.start());

    return () => {
      animations.forEach((animation) => animation.stop());
    };
  }, [dot1, dot2, dot3]);

  return (
    <View
      accessibilityLabel="Assistant is thinking"
      style={{
        flexDirection: 'row',
        alignItems: 'center',
        gap: 8,
      }}>
      <CText variant="body" style={{ color: theme.color10.val }}>
        Thinking
      </CText>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
        <Animated.View style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: theme.color9.val, opacity: dot1 }} />
        <Animated.View style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: theme.color9.val, opacity: dot2 }} />
        <Animated.View style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: theme.color9.val, opacity: dot3 }} />
      </View>
    </View>
  );
};
