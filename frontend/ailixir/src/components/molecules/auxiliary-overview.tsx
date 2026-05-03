import { CText } from '@/components/atoms';
import { YStack } from 'tamagui';

export function AuxiliaryOverview({ items }: { items: string[] }) {
  return (
    <YStack mt={28} gap={4}>
      {items.map((item) => (
        <CText key={item} variant="caption">
          {item}
        </CText>
      ))}
    </YStack>
  );
}
