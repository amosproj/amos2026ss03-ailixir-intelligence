import { AuthFooterLink, ScreenHeader } from '@/components/molecules';
import { SignUpForm } from '@/components/organisms';
import { useRouter } from 'expo-router';
import React, { useState } from 'react';
import { YStack } from 'tamagui';
import { useSignUp } from '@/hooks/useSignUp';

const PASSWORD_MIN_LENGTH = 8;

type SignUpFormValues = {
  email: string;
  firstName: string;
  lastName: string;
  password: string;
};

export default function SignUpScreen() {
  const router = useRouter();
  const [error, setError] = useState('');
  const { mutateAsync: signUpAsync, isPending } = useSignUp();

  const handleSignUp = async (data: { email: string; password: string }) => {
    try {
      setError('');
<<<<<<< HEAD
      console.log('before signup');
      await signUpAsync({
        email: data.email,
        password: data.password,
        first_name: data.firstName,
        last_name: data.lastName,
      });
      router.push('./login');
=======
      await createUserWithEmailAndPassword(auth, data.email, data.password);
      router.replace('./login');
>>>>>>> 61c679f (fix: use replace for stack navigation)
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
        <SignUpForm onSubmit={handleSignUp} serverError={error} />
      </YStack>
      <AuthFooterLink text="Already have an account?" linkLabel="Sign in" onPress={() => router.replace('./login')} />
    </YStack>
  );
}
