import { AuthFooterLink, ScreenHeader } from '@/components/molecules';
import { LoginForm } from '@/components/organisms';
import { useAuth } from '@/hooks/useAuth';
import { AuthError } from '@/lib/auth-errors';
import { useRouter } from 'expo-router';
import React, { useState } from 'react';
import { YStack } from 'tamagui';

export default function LoginScreen() {
  const router = useRouter();
  const { signIn } = useAuth();
  const [error, setError] = useState('');

  const handleLogin = async (data: { email: string; password: string }) => {
    setError('');
    try {
      await signIn(data.email, data.password);
    } catch (e) {
      setError(e instanceof AuthError ? e.userMessage : 'Something went wrong. Please try again.');
    }
  };

  return (
    <YStack flex={1} width="100%" background="$background" justify="space-between" items="stretch" py={24}>
      <YStack></YStack>
      <YStack width="100%" gap={20}>
        <ScreenHeader title="Welcome back" subtitle="Log in to continue" />
        <LoginForm onForgotPasswordPress={() => {}} onSubmit={handleLogin} serverError={error} />
      </YStack>
      <AuthFooterLink text="Don't have an account?" linkLabel="Sign Up" onPress={() => router.replace('./signup')} />
    </YStack>
  );
}
