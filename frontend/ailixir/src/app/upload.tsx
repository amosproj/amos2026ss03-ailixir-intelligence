import * as DocumentPicker from 'expo-document-picker';
import { useState } from 'react';
import { SafeAreaView } from 'react-native-safe-area-context';

import { CButton, CText } from '@/components/atoms';
import { YStack } from '@tamagui/stacks';

export default function UploadScreen() {
  const [uploadedFiles, setUploadedFiles] = useState<DocumentPicker.DocumentPickerAsset[]>([]);

  const handlePickFiles = async () => {
    const pickerResult = await DocumentPicker.getDocumentAsync({
      type: ['application/pdf', 'image/*'],
      multiple: true,
      copyToCacheDirectory: true,
    });

    if (pickerResult.canceled) {
      return;
    }

    setUploadedFiles(pickerResult.assets);
  };

  return (
    <SafeAreaView>
      <YStack gap={5} width={300}>
        <CButton onPress={handlePickFiles}>Upload File</CButton>
        {uploadedFiles.map((file, index) => (
          <CText key={`${file.uri}-${index}`}>{file.name}</CText>
        ))}
      </YStack>
    </SafeAreaView>
  );
}
