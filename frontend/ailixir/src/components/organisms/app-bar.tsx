import { CText } from '@/components/atoms';
import { Circle, XStack } from 'tamagui';

export function AppBar() {
  return (
    <>
      <XStack gap={10} justify="space-between" width={300}>
        <CText fontSize={40} fontWeight="bold">
          AiLixir
        </CText>
        <Circle size={40} background="blue" />
      </XStack>
    </>
  );
}
