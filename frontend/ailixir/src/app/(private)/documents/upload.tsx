import * as DocumentPicker from 'expo-document-picker';
import { useState } from 'react';
import { ActivityIndicator } from 'react-native';

import { CButton, CText } from '@/components/atoms';
import { YStack } from '@tamagui/stacks';
import { useFileUpload } from '@/hooks/useFileUpload';

export default function UploadScreen() {
  const [selectedFiles, setSelectedFiles] = useState<DocumentPicker.DocumentPickerAsset[]>([]);
  const { uploadFileAsync, isUploading, uploadProgress } = useFileUpload();

  const handlePickFiles = async () => {
    const pickerResult = await DocumentPicker.getDocumentAsync({
      type: ['application/pdf', 'image/*'],
      multiple: true,
      copyToCacheDirectory: true,
    });

    if (pickerResult.canceled) return;

    setSelectedFiles(pickerResult.assets);
  };

  const handleStartUpload = async () => {
    if (selectedFiles.length === 0) return;

    try {
      for (const file of selectedFiles) {
        await uploadFileAsync({
          uri: file.uri,
          name: file.name,
          type: file.mimeType || 'application/octet-stream',
        });
      }

      setSelectedFiles([]);
      alert('all files have been uploaded successfully');
    } catch (error) {
      alert('an error occured: ' + String(error));
    }
  };

  return (
    <YStack width={'100%'} px={20} py={20} height={'100%'} justify={'space-between'}>
      {isUploading && <ActivityIndicator size="small" />}

      <CButton emphasis="high" fullWidth onPress={handlePickFiles} disabled={isUploading}>
        Dateien auswählen
      </CButton>

      <YStack gap={5}>
        {selectedFiles.map((file, index) => (
          <CText key={`${file.uri}-${index}`} fontSize={14} color="gray">
            {file.name} ({(file.size ? file.size / 1024 / 1024 : 0).toFixed(2)} MB)
          </CText>
        ))}
      </YStack>

      {selectedFiles.length > 0 && (
        <CButton emphasis="high" fullWidth onPress={handleStartUpload} disabled={isUploading}>
          {isUploading ? `Hochladen... ${uploadProgress}%` : 'Upload starten'}
        </CButton>
      )}
    </YStack>
  );
}
