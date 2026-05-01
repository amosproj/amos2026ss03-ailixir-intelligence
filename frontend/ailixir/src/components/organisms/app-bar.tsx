import { CButton, CText } from '@/components/atoms';
import { ChevronLeft } from '@tamagui/lucide-icons-2';
import { useRouter } from 'expo-router';
import { Circle, XStack } from 'tamagui';

export function AppBar() {
  const router = useRouter();

  return (
    <>
      <XStack gap={10} justify="space-between" width={300}>
        <CButton icon={ChevronLeft} onPress={() => router.back()}></CButton>
        <CText fontSize={40} fontWeight="bold">
          AiLixir
        </CText>
        <Circle size={40} background="blue" />
      </XStack>
    </>
  );
}
