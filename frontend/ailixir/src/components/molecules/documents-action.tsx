import { CButton } from '@/components/atoms';
import { ActionPair } from '@/components/molecules';
import { ChevronRight, Upload } from '@tamagui/lucide-icons-2';
import { YStack } from 'tamagui';

type DocumentsActionProps = {
  onUploadDocument: () => void;
  onScanDocument: () => void;
};

export function DocumentsAction({ onUploadDocument, onScanDocument }: DocumentsActionProps) {
  return (
    <YStack mt={170}>
      <ActionPair
        leftAction={
          <CButton iconButton icon={Upload} emphasis="low" onPress={onUploadDocument}>
            upload
          </CButton>
        }
        rightAction={
          <CButton iconButton icon={ChevronRight} emphasis="high" onPress={onScanDocument}>
            scan
          </CButton>
        }
      />
    </YStack>
  );
}
