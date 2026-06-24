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

  // On success: do NOT navigate here. `Stack.Protected` in the root layout
  // is the single source of truth for routing — when Firebase fires
  // `onAuthStateChanged`, the guard flips and the user is moved to
  // `(private)`. A manual `router.push('./success')` races that swap and
  // on slow / cold-storage devices loses, leaving the user stuck on this
  // screen (issue #208).
  const handleLogin = async (data: { email: string; password: string }) => {
    setError('');
    try {
      await signIn(data.email, data.password);
    } catch (e) {
      // `useAuth().signIn` always throws `AuthError`; the `userMessage` is
      // safe to render. Any other shape is a programming error we want to
      // surface during dev, not silently swallow.
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
