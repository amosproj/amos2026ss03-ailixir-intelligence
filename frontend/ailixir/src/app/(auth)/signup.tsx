import { CText } from '@/components/atoms';
import { router } from 'expo-router';
import React from 'react';

export default function SignUpScreen() {
  return (
    <>
      <CText>SignUp Page</CText>

      <CText fontSize={12} color="darkgray">
        Already have an account?{' '}
        <CText color="$blue10" onPress={() => router.push('/(auth)/login')}>
          Sign In
        </CText>
      </CText>
    </>
  );
}
