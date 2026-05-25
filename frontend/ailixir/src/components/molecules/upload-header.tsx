import { CText } from '@/components/atoms';
import { YStack } from 'tamagui';

type UploadHeaderProps = {
  title: string;
  subtitle: string;
};

export function UploadHeader({ title, subtitle }: UploadHeaderProps) {
  return (
    <YStack gap={8}>
      <CText variant="h2">{title}</CText>
      <CText variant="body">{subtitle}</CText>
    </YStack>
  );
}
