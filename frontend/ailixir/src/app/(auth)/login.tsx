import { CText } from '@/components/atoms';
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
    <YStack width="100%" height="100%" background="$background" justify="center" items="center" gap={5}>
      <LoginForm onForgotPasswordPress={() => {}} onSubmit={handleLogin} />
      {error ? (
        <CText variant="body" color="red">
          {error}
        </CText>
      ) : null}
      <CText variant="body" color="darkgray">
        Don{"'"}t have an account?{' '}
        <CText color="$blue10" onPress={() => router.push('./signup')}>
          Sign Up
        </CText>
      </CText>
    </YStack>
  );
}
