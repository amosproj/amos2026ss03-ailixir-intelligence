import { CText } from '@/components/atoms';
import { YStack } from 'tamagui';

type ScreenHeaderProps = {
  title: string;
  subtitle?: string;
};

export function ScreenHeader({ title, subtitle }: ScreenHeaderProps) {
  return (
    <YStack gap={8}>
      <CText variant="h2">{title}</CText>
      {subtitle ? <CText variant="body">{subtitle}</CText> : null}
    </YStack>
  );
}
