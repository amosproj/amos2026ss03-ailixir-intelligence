import { CText } from '@/components/atoms';
import { router } from 'expo-router';
import React from 'react';
import { YStack } from 'tamagui';

export default function SignUpScreen() {
  return (
    <YStack width="100%" height="100%" background="$background" justify="center" items="center" gap={10}>
      <CText>SignUp Page</CText>

      <CText variant="caption" color="darkgray">
        Already have an account?{' '}
        <CText color="$blue10" onPress={() => router.push('/(auth)/login')}>
          Sign In
        </CText>
      </CText>
    </YStack>
  );
}
