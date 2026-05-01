import { CText } from '@/components/atoms';
import React from 'react';
import { YStack } from 'tamagui';

export default function SuccessScreen() {
  return (
    <YStack width="100%" height="100%" background="$background" justify="center" items="center" gap={10}>
      <CText fontSize={16} color="green" fontWeight={600}>
        logged in 💯
      </CText>
    </YStack>
  );
}
