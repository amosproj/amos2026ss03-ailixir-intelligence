import { CButton, CInput, CText } from '@/components/atoms';
import { ChevronRight } from '@tamagui/lucide-icons-2';
import { useRouter } from 'expo-router';
import React, { useState } from 'react';
import { Controller, useForm } from 'react-hook-form';
import { ScrollView } from 'react-native';
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

  const {
    control,
    handleSubmit,
    formState: { errors },
  } = useForm<SignUpFormValues>({
    defaultValues: {
      email: '',
      firstName: '',
      lastName: '',
      password: '',
    },
  });

  const onSubmit = handleSubmit(async (data) => {
    try {
      setError('');
      console.log('before signup');
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
  });

  return (
    <ScrollView style={{ flex: 1 }} contentContainerStyle={{ flexGrow: 1 }} showsVerticalScrollIndicator={false}>
      <YStack flex={1} background="$background" px={24} pt={32} pb={28} gap={24}>
        <YStack flex={1} justify="center" gap={18}>
          <YStack gap={8}>
            <CText variant="h2" color="$color11">
              Sign Up
            </CText>
          </YStack>

          <YStack gap={12}>
            <YStack gap={6}>
              <CText variant="caption">E-Mail</CText>
              <Controller
                name="email"
                control={control}
                rules={{
                  required: 'Email is required',
                  validate: (value) => value.includes('@') || 'Invalid email address',
                }}
                render={({ field: { onBlur, onChange, value } }) => (
                  <CInput placeholder="john.doe@example.com" theme="bright" width="100%" value={value} onBlur={onBlur} onChangeText={onChange} autoCapitalize="none" keyboardType="email-address" />
                )}
              />

              {errors.email?.message ? (
                <CText variant="caption" color="$red10">
                  {errors.email.message}
                </CText>
              ) : null}
            </YStack>

            <YStack gap={6}>
              <CText variant="caption">First Name</CText>
              <Controller
                name="firstName"
                control={control}
                rules={{ required: 'First name is required' }}
                render={({ field: { onBlur, onChange, value } }) => (
                  <CInput placeholder="John" theme="bright" width="100%" value={value} onBlur={onBlur} onChangeText={onChange} autoCapitalize="words" />
                )}
              />

              {errors.firstName?.message ? (
                <CText variant="caption" color="$red10">
                  {errors.firstName.message}
                </CText>
              ) : null}
            </YStack>

            <YStack gap={6}>
              <CText variant="caption">Last Name</CText>
              <Controller
                name="lastName"
                control={control}
                rules={{ required: 'Last name is required' }}
                render={({ field: { onBlur, onChange, value } }) => (
                  <CInput placeholder="Doe" theme="bright" width="100%" value={value} onBlur={onBlur} onChangeText={onChange} autoCapitalize="words" />
                )}
              />

              {errors.lastName?.message ? (
                <CText variant="caption" color="$red10">
                  {errors.lastName.message}
                </CText>
              ) : null}
            </YStack>

            <YStack gap={6}>
              <CText variant="caption">Password</CText>
              <Controller
                name="password"
                control={control}
                rules={{
                  required: 'Password is required',
                  minLength: {
                    value: PASSWORD_MIN_LENGTH,
                    message: `Password required at least ${PASSWORD_MIN_LENGTH} characters`,
                  },
                }}
                render={({ field: { onBlur, onChange, value } }) => <CInput placeholder="password" theme="bright" width="100%" value={value} onBlur={onBlur} onChangeText={onChange} secureTextEntry />}
              />

              {errors.password?.message ? (
                <CText variant="caption" color="$red10">
                  {errors.password.message}
                </CText>
              ) : null}
            </YStack>
          </YStack>

          {error ? (
            <CText variant="caption" color="$red10">
              {error}
            </CText>
          ) : null}

          <CButton theme="blue" iconButton icon={ChevronRight} onPress={onSubmit} width="100%" disabled={isPending} opacity={isPending ? 0.6 : 1}>
            {isPending ? 'creating account...' : 'continue'}
          </CButton>
        </YStack>

        <YStack items="center" gap={4}>
          <CText variant="caption" color="$color9">
            Already have an Account?{' '}
            <CText color="$blue10" onPress={() => router.replace('./login')}>
              sign in
            </CText>
          </CText>
        </YStack>
      </YStack>
    </ScrollView>
  );
}
