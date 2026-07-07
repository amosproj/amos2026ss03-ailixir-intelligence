import React, { useEffect, useRef } from 'react';
import { Animated, Easing, StyleSheet, View, TouchableOpacity } from 'react-native';
import { Mic, AudioWaveform } from '@tamagui/lucide-icons-2';

interface VoicePulseCircleProps {
  status: string;
  isSpeaking: boolean;
  isListening: boolean;
  isLoading: boolean;
  onPress: () => void;
}

export function VoicePulseCircle({ status, isSpeaking, isListening, isLoading, onPress }: VoicePulseCircleProps) {
  const isActive = status === 'connected' || status === 'connecting';
  const isConnecting = status === 'connecting';
  const isConnected = status === 'connected';

  const pulseAnim1 = useRef(new Animated.Value(0)).current;
  const pulseAnim2 = useRef(new Animated.Value(0)).current;
  const centerScale = useRef(new Animated.Value(1)).current;

  useEffect(() => {
    if (isActive) {
      pulseAnim1.setValue(0);
      pulseAnim2.setValue(0);

      const speed = isSpeaking ? 1500 : isListening ? 2200 : 3000;

      const anim1 = Animated.loop(
        Animated.timing(pulseAnim1, {
          toValue: 1,
          duration: speed,
          easing: Easing.out(Easing.ease),
          useNativeDriver: true,
        }),
      );

      const anim2 = Animated.loop(
        Animated.timing(pulseAnim2, {
          toValue: 1,
          duration: speed,
          easing: Easing.out(Easing.ease),
          useNativeDriver: true,
        }),
      );

      anim1.start();

      const delayTimeout = setTimeout(() => {
        anim2.start();
      }, speed / 2);

      return () => {
        anim1.stop();
        anim2.stop();
        clearTimeout(delayTimeout);
      };
    } else {
      pulseAnim1.setValue(0);
      pulseAnim2.setValue(0);
    }
  }, [isActive, isSpeaking, isListening, pulseAnim1, pulseAnim2]);

  useEffect(() => {
    if (isConnected) {
      centerScale.setValue(1);
      let anim: Animated.CompositeAnimation | null = null;

      if (isSpeaking) {
        anim = Animated.loop(
          Animated.sequence([
            Animated.timing(centerScale, {
              toValue: 1.12,
              duration: 450,
              easing: Easing.inOut(Easing.ease),
              useNativeDriver: true,
            }),
            Animated.timing(centerScale, {
              toValue: 1.0,
              duration: 450,
              easing: Easing.inOut(Easing.ease),
              useNativeDriver: true,
            }),
          ]),
        );
      } else if (isListening) {
        anim = Animated.loop(
          Animated.sequence([
            Animated.timing(centerScale, {
              toValue: 1.06,
              duration: 1000,
              easing: Easing.inOut(Easing.ease),
              useNativeDriver: true,
            }),
            Animated.timing(centerScale, {
              toValue: 1.0,
              duration: 1000,
              easing: Easing.inOut(Easing.ease),
              useNativeDriver: true,
            }),
          ]),
        );
      }

      if (anim) {
        anim.start();
      }

      return () => {
        if (anim) {
          anim.stop();
        }
        Animated.timing(centerScale, {
          toValue: 1,
          duration: 300,
          useNativeDriver: true,
        }).start();
      };
    } else {
      Animated.timing(centerScale, {
        toValue: 1,
        duration: 300,
        useNativeDriver: true,
      }).start();
    }
  }, [isConnected, isSpeaking, isListening, centerScale]);

  let Icon = Mic;
  if (isConnecting || isConnected) {
    Icon = AudioWaveform;
  }

  const scale1 = pulseAnim1.interpolate({
    inputRange: [0, 1],
    outputRange: [1, 2],
  });
  const opacity1 = pulseAnim1.interpolate({
    inputRange: [0, 1],
    outputRange: [0.4, 0],
  });

  const scale2 = pulseAnim2.interpolate({
    inputRange: [0, 1],
    outputRange: [1, 2],
  });
  const opacity2 = pulseAnim2.interpolate({
    inputRange: [0, 1],
    outputRange: [0.4, 0],
  });

  return (
    <View style={styles.pulseContainer}>
      {isActive && (
        <>
          <Animated.View
            style={[
              styles.ripple,
              {
                transform: [{ scale: scale1 }],
                opacity: opacity1,
                backgroundColor: '#847EF3',
              },
            ]}
          />
          <Animated.View
            style={[
              styles.ripple,
              {
                transform: [{ scale: scale2 }],
                opacity: opacity2,
                backgroundColor: '#847EF3',
              },
            ]}
          />
        </>
      )}

      <Animated.View style={{ transform: [{ scale: centerScale }] }}>
        <TouchableOpacity
          activeOpacity={0.8}
          onPress={onPress}
          disabled={isLoading}
          style={[
            styles.mainCircle,
            {
              backgroundColor: isConnecting || isConnected ? '#847EF3' : '#F4F4F4',
              shadowColor: isConnected ? '#847EF3' : '#000000',
              shadowOpacity: isConnected ? 0.4 : 0.1,
              shadowRadius: isConnected ? 12 : 6,
              elevation: isConnected ? 8 : 2,
            },
          ]}>
          <Icon size={40} color={isConnecting || isConnected ? '#FFFFFF' : '#7D7D7D'} />
        </TouchableOpacity>
      </Animated.View>
    </View>
  );
}

const styles = StyleSheet.create({
  pulseContainer: {
    justifyContent: 'center',
    alignItems: 'center',
    height: 220,
    width: '100%',
  },
  mainCircle: {
    width: 110,
    height: 110,
    borderRadius: 55,
    justifyContent: 'center',
    alignItems: 'center',
    zIndex: 2,
  },
  ripple: {
    position: 'absolute',
    width: 110,
    height: 110,
    borderRadius: 55,
    zIndex: 1,
  },
});
