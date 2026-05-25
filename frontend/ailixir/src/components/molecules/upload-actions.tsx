import { ActivityIndicator } from 'react-native';
import { XStack, YStack } from 'tamagui';

import { CButton, CText } from '@/components/atoms';

type UploadActionsProps = {
  isBusy: boolean;
  hasFiles: boolean;
  onStartUpload: () => void;
};

export function UploadActions({ isBusy, hasFiles, onStartUpload }: UploadActionsProps) {
  return (
    <YStack gap={12}>
      {isBusy && (
        <XStack items="center" gap={10} px={14} py={12}>
          <ActivityIndicator size="small" />
          <CText variant="body" color="#111111">
            Upload in progress...
          </CText>
        </XStack>
      )}

      {hasFiles && (
        <CButton emphasis="high" fullWidth onPress={onStartUpload} disabled={isBusy}>
          {isBusy ? 'Uploading... ' : 'Start upload'}
        </CButton>
      )}
    </YStack>
  );
}
