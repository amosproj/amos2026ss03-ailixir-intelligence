import { CButton, CText } from '@/components/atoms';
import { Circle, XStack } from 'tamagui';
import { useRouter } from 'expo-router';

export function AppBar() {
  const router = useRouter();

  return (
    <>
      <XStack gap={10} justify="space-between" width={300}>
        <CText fontSize={40} fontWeight="bold">
          AiLixir
        </CText>
        <CButton onPress={() => router.back()}>Back</CButton>
        <Circle size={40} background="blue" />
      </XStack>
    </>
  );
}
