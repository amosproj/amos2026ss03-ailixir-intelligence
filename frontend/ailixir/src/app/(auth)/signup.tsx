import { useRouter } from 'expo-router';
import React, { useState } from 'react';
import type { SubmitHandler } from 'react-hook-form';
import { YStack } from 'tamagui';
import { useSignUp } from '@/hooks/useSignUp';
import { ScreenHeader, AuthFooterLink } from '@/components/molecules';
import { SignUpForm, type SignUpFormValues } from '@/components/organisms';

export default function SignUpScreen() {
  const router = useRouter();
  const [error, setError] = useState('');
  const { mutateAsync: signUpAsync } = useSignUp();

  const onSubmit: SubmitHandler<SignUpFormValues> = async (data) => {
    try {
      setError('');
      await signUpAsync({
        email: data.email,
        password: data.password,
        first_name: data.firstName,
        last_name: data.lastName,
      });
      router.push('./login');
    } catch (e: unknown) {
      const message = e instanceof Error ? e.message : 'An unexpected error occurred';
      setError(message);
    }
  };

  return (
    <YStack flex={1} width="100%" background="$background" justify="space-between" items="stretch" py={24}>
      <YStack></YStack>
      <YStack width="100%" gap={20}>
        <ScreenHeader title="Create your account" subtitle="Set up your workspace in a few steps." />
        <SignUpForm onSubmit={onSubmit} serverError={error} />
      </YStack>
      <AuthFooterLink text="Already have an account?" linkLabel="Sign in" onPress={() => router.replace('./login')} />
    </YStack>
  );
}
