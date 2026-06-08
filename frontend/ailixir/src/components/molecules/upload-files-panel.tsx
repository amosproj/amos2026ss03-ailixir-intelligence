import * as DocumentPicker from 'expo-document-picker';
import { Trash } from '@tamagui/lucide-icons-2';
import { XStack, YStack } from 'tamagui';

import { CButton, CText } from '@/components/atoms';
import { formatSize } from '@/utils/format';

type UploadFilesPanelProps = {
  files: DocumentPicker.DocumentPickerAsset[];
  isBusy: boolean;
  onPickFiles: () => void;
  onRemoveFile: (uri: string) => void;
};

export function UploadFilesPanel({ files, isBusy, onPickFiles, onRemoveFile }: UploadFilesPanelProps) {
  const filesLabel = files.length === 0 ? 'No files selected yet' : `${files.length} file${files.length > 1 ? 's' : ''} ready`;

  return (
    <YStack gap={16} px={16} py={18} bg="$accent12">
      <XStack items="center" justify="space-between">
        <YStack gap={4}>
          <CText variant="lead">Files</CText>
          <CText variant="caption">{filesLabel}</CText>
        </YStack>

        <CButton emphasis="high" onPress={onPickFiles} disabled={isBusy}>
          Choose files
        </CButton>
      </XStack>

      <YStack gap={12}>
        {files.map((file, index) => (
          <XStack key={`${file.uri}-${index}`} items="center" justify="space-between" bg="#F9F7F2" px={14} py={12} gap={12}>
            <YStack flex={1} gap={4}>
              <CText variant="body" numberOfLines={1}>
                {file.name}
              </CText>
              <CText variant="caption">
                {file.mimeType || 'Unknown type'} · {formatSize(file.size)}
              </CText>
            </YStack>
            <XStack items="center" gap={8}>
              <YStack>
                <CText variant="caption">Ready</CText>
              </YStack>
              <CButton icon={Trash} onPress={() => onRemoveFile(file.uri)} disabled={isBusy}></CButton>
            </XStack>
          </XStack>
        ))}
      </YStack>
    </YStack>
  );
}
