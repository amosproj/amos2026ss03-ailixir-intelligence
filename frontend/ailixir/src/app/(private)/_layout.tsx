import { AppBar } from '@/components/organisms';
import { Stack } from 'expo-router';
import React from 'react';

export default function PrivateLayout() {
  return (
    <>
      <AppBar />
      <Stack screenOptions={{ headerShown: false }} />
    </>
  );
}
