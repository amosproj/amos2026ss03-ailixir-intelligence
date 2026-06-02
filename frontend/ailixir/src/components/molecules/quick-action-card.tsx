import type { QuickAction } from '@/data/home';

import { CText } from '@/components/atoms';
import { Link } from 'expo-router';
import { YStack } from 'tamagui';

type QuickActionCardProps = {
  action: QuickAction;
};

export function QuickActionCard({ action }: QuickActionCardProps) {
  const Icon = action.icon;

  return (
    <Link href={action.href} asChild>
      <YStack flex={1} gap={14} p={20} bg="$accent12" items="center" justify="center" style={{ minWidth: 160, minHeight: 180 }}>
        <YStack width={64} height={64} items="center" justify="center" bg={action.iconBackground}>
          <Icon size={action.iconSize} color="$accent12" strokeWidth={action.iconStrokeWidth} />
        </YStack>
        <YStack gap={4} items="center">
          <CText variant="h2">{action.title}</CText>
          <CText variant="body">{action.subtitle}</CText>
        </YStack>
      </YStack>
    </Link>
  );
}
