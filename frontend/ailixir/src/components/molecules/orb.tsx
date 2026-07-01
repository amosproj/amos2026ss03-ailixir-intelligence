'use client';

import React, { useEffect, useMemo, useRef } from 'react';
import { Animated, Easing, View, useColorScheme } from 'react-native';
import Svg, { Circle, Defs, LinearGradient, RadialGradient, Stop } from 'react-native-svg';
import { CText } from '@/components/atoms';

export type AgentState = null | 'thinking' | 'listening' | 'talking';

type OrbProps = {
  colors?: [string, string];
  colorsRef?: React.RefObject<[string, string]>;
  resizeDebounce?: number;
  seed?: number;
  agentState?: AgentState;
  volumeMode?: 'auto' | 'manual';
  manualInput?: number;
  manualOutput?: number;
  inputVolumeRef?: React.RefObject<number>;
  outputVolumeRef?: React.RefObject<number>;
  getInputVolume?: () => number;
  getOutputVolume?: () => number;
  className?: string;
};

export function Orb({
  colors = ['#CADCFC', '#A0B9D1'],
  agentState = null,
  volumeMode = 'auto',
  manualInput,
  manualOutput,
  inputVolumeRef,
  outputVolumeRef,
  getInputVolume,
  getOutputVolume,
}: OrbProps) {
  const colorScheme = useColorScheme();
  const isDark = colorScheme === 'dark';
  const pulseAnim = useRef(new Animated.Value(0.96)).current;
  const glowAnim = useRef(new Animated.Value(0.2)).current;
  const orbitAnim = useRef(new Animated.Value(0)).current;

  const resolvedColors = useMemo(() => {
    const [colorA, colorB] = colors;
    return {
      primary: colorA ?? '#CADCFC',
      secondary: colorB ?? '#A0B9D1',
      accent: isDark ? '#FFFFFF' : '#6B7280',
    };
  }, [colors, isDark]);

  const activeVolume = useMemo(() => {
    if (volumeMode === 'manual') {
      const inputValue = clamp01(manualInput ?? inputVolumeRef?.current ?? getInputVolume?.() ?? 0);
      const outputValue = clamp01(manualOutput ?? outputVolumeRef?.current ?? getOutputVolume?.() ?? 0);

      if (agentState === 'listening' || agentState === null) {
        return inputValue;
      }

      return outputValue;
    }

    switch (agentState) {
      case 'listening':
      case null:
        return 0.7;
      case 'talking':
        return 0.85;
      case 'thinking':
        return 0.45;
      default:
        return 0.2;
    }
  }, [agentState, volumeMode, manualInput, manualOutput, inputVolumeRef, outputVolumeRef, getInputVolume, getOutputVolume]);

  useEffect(() => {
    const pulseDuration = agentState === 'talking' ? 700 : agentState === 'listening' ? 900 : agentState === 'thinking' ? 1400 : 1800;

    const pulseLoop = Animated.loop(
      Animated.sequence([
        Animated.timing(pulseAnim, { toValue: 1.03, duration: pulseDuration, easing: Easing.inOut(Easing.ease), useNativeDriver: true }),
        Animated.timing(pulseAnim, { toValue: 0.95, duration: pulseDuration, easing: Easing.inOut(Easing.ease), useNativeDriver: true }),
      ]),
    );

    const glowLoop = Animated.loop(
      Animated.sequence([
        Animated.timing(glowAnim, { toValue: 0.45, duration: 1100, easing: Easing.inOut(Easing.ease), useNativeDriver: true }),
        Animated.timing(glowAnim, { toValue: 0.18, duration: 1100, easing: Easing.inOut(Easing.ease), useNativeDriver: true }),
      ]),
    );

    const orbitLoop = Animated.loop(Animated.timing(orbitAnim, { toValue: 1, duration: 2200, easing: Easing.linear, useNativeDriver: true }));

    pulseLoop.start();
    glowLoop.start();
    orbitLoop.start();

    return () => {
      pulseLoop.stop();
      glowLoop.stop();
      orbitLoop.stop();
    };
  }, [agentState, glowAnim, orbitAnim, pulseAnim]);

  const pulseScale = pulseAnim.interpolate({ inputRange: [0.95, 1.03], outputRange: [0.95, 1.03] });
  const orbitRotation = orbitAnim.interpolate({ inputRange: [0, 1], outputRange: ['0deg', '360deg'] });
  const ringOpacity = 0.35 + activeVolume * 0.45;
  const glowOpacity = glowAnim.interpolate({ inputRange: [0.18, 0.45], outputRange: [0.16, 0.4] });

  return (
    <View style={{ alignItems: 'center', justifyContent: 'center' }}>
      <View style={{ width: 128, height: 128, borderRadius: 64, alignItems: 'center', justifyContent: 'center' }}>
        <Animated.View pointerEvents="none" style={{ width: 128, height: 128, transform: [{ scale: pulseScale }] }}>
          <Svg width="128" height="128" viewBox="0 0 128 128">
            <Defs>
              <RadialGradient id="orbGradient" cx="50%" cy="40%" rx="65%" ry="65%">
                <Stop offset="0%" stopColor={resolvedColors.primary} stopOpacity="1" />
                <Stop offset="100%" stopColor={resolvedColors.secondary} stopOpacity="0.95" />
              </RadialGradient>
              <LinearGradient id="ringGradient" x1="0%" y1="0%" x2="100%" y2="100%">
                <Stop offset="0%" stopColor={resolvedColors.primary} stopOpacity="0.95" />
                <Stop offset="100%" stopColor={resolvedColors.secondary} stopOpacity="0.85" />
              </LinearGradient>
            </Defs>

            <Circle cx="64" cy="64" r="44" fill="url(#orbGradient)" />
            <Circle cx="64" cy="64" r="42" fill="none" stroke={resolvedColors.accent} strokeOpacity={0.16} strokeWidth={2} />
            <Circle cx="64" cy="64" r="50" fill="none" stroke="url(#ringGradient)" strokeOpacity={ringOpacity} strokeWidth={3} />
            <Animated.View style={{ position: 'absolute', left: 0, top: 0, width: 128, height: 128, transform: [{ rotate: orbitRotation }] }}>
              <Circle cx="64" cy="18" r="6" fill={resolvedColors.primary} fillOpacity={0.8} />
              <Circle cx="64" cy="110" r="5" fill={resolvedColors.secondary} fillOpacity={0.65} />
            </Animated.View>
          </Svg>
        </Animated.View>

        <Animated.View
          pointerEvents="none"
          style={{
            position: 'absolute',
            width: 140,
            height: 140,
            borderRadius: 70,
            backgroundColor: resolvedColors.primary,
            opacity: glowOpacity,
            transform: [{ scale: pulseScale }],
          }}
        />
      </View>

      {agentState === 'listening' ? (
        <CText variant="caption" style={{ marginTop: 12 }}>
          Listening...
        </CText>
      ) : null}
    </View>
  );
}

function clamp01(n: number) {
  if (!Number.isFinite(n)) return 0;
  return Math.min(1, Math.max(0, n));
}
