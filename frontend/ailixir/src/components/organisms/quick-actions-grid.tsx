import type { QuickAction } from '@/data/home';

import { QuickActionCard } from '@/components/molecules';
import { XStack } from 'tamagui';

type QuickActionsGridProps = {
  actions: QuickAction[];
};

export function QuickActionsGrid({ actions }: QuickActionsGridProps) {
  return (
    <XStack gap={12} width="100%" flexWrap="nowrap">
      {actions.map((action) => (
        <QuickActionCard key={action.title} action={action} />
      ))}
    </XStack>
  );
}
