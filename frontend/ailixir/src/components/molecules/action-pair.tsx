import type { ReactNode } from 'react';

import { XStack } from 'tamagui';

type ActionPairProps = {
  leftAction: ReactNode;
  rightAction: ReactNode;
};

export function ActionPair({ leftAction, rightAction }: ActionPairProps) {
  return (
    <XStack justify="flex-end" items="center" gap={16}>
      {leftAction}
      {rightAction}
    </XStack>
  );
}
