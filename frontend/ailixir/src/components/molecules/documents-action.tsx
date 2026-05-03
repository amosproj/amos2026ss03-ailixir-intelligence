import { CButton } from '@/components/atoms';
import { ChevronRight, Upload } from '@tamagui/lucide-icons-2';
import { XStack } from 'tamagui';

type DocumentsActionProps = {
  onUploadDocument: () => void;
  onScanDocument: () => void;
};

export function DocumentsAction({ onUploadDocument, onScanDocument }: DocumentsActionProps) {
  return (
    <XStack mt={170} justify="flex-end" items="center" gap={16}>
      <CButton iconButton icon={Upload} emphasis="low" onPress={onUploadDocument}>
        upload
      </CButton>
      <CButton iconButton icon={ChevronRight} emphasis="high" onPress={onScanDocument}>
        scan
      </CButton>
    </XStack>
  );
}
