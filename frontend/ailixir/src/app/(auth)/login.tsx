import { CText } from '@/components/atoms';
import { LoginForm } from '@/components/organisms';
import { useRouter } from 'expo-router';
import React from 'react';
import { YStack } from 'tamagui';

export default function LoginScreen() {
  const router = useRouter();

  // TODO: this is unsafe, we should use <Stack.Protected> once we have proper routing
  const handleLogin = () => {
    router.push('./success');
  };

  return (
    <YStack width="100%" height="100%" background="$background" justify="center" items="center" gap={5}>
      <LoginForm onForgotPasswordPress={() => {}} onSubmit={handleLogin} />
      <CText variant="body" color="darkgray">
        Don{"'"}t have an account?{' '}
        <CText color="$blue10" onPress={() => router.push('./signup')}>
          Sign Up
        </CText>
      </CText>
    </YStack>
  );
}
