import { CText } from '@/components/atoms';
import { LoginForm } from '@/components/organisms';
import { AppBar } from '@/components/organisms/app-bar';
import { useRouter } from 'expo-router';
import React from 'react';
import { SafeAreaView } from 'react-native-safe-area-context';
import { YStack } from 'tamagui';

export default function LoginScreen() {
  const router = useRouter();

  // TODO: this is unsafe, we should use <Stack.Protected> once we have proper routing
  const handleLogin = () => {
    router.push('/login-success');
  };

  return (
    <SafeAreaView>
      <YStack width="100%" height="100%" background="$background" justify="space-between" items="center" gap={5}>
        <AppBar />
        <LoginForm onForgotPasswordPress={() => {}} onSubmit={handleLogin} />
        <CText fontSize={12} color="darkgray">
          Don{"'"}t have an account?{' '}
          <CText color="$blue10" onPress={() => {}}>
            Sign Up
          </CText>
        </CText>
      </YStack>
    </SafeAreaView>
  );
}
