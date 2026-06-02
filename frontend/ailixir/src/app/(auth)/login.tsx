import { AuthFooterLink, ScreenHeader } from '@/components/molecules';
import { LoginForm } from '@/components/organisms';
import { auth } from '@/lib/firebase';
import { useRouter } from 'expo-router';
import { signInWithEmailAndPassword } from 'firebase/auth';
import React, { useState } from 'react';
import { YStack } from 'tamagui';

export default function LoginScreen() {
  const router = useRouter();
  const [error, setError] = useState('');

  const handleLogin = async (data: { email: string; password: string }) => {
    try {
      setError('');
      await signInWithEmailAndPassword(auth, data.email, data.password);
      router.push('./success');
    } catch (e: unknown) {
      const message = e instanceof Error ? e.message : 'An unexpected error occurred';
      setError(message);
    }
  };

  return (
    <YStack flex={1} width="100%" background="$background" justify="space-between" items="stretch" py={24}>
      <YStack></YStack>
      <YStack width="100%" gap={20}>
        <ScreenHeader title="Welcome back" subtitle="Log in to continue" />
        <LoginForm onForgotPasswordPress={() => {}} onSubmit={handleLogin} serverError={error} />
      </YStack>
      <AuthFooterLink text="Don't have an account?" linkLabel="Sign Up" onPress={() => router.push('./signup')} />
    </YStack>
  );
}
