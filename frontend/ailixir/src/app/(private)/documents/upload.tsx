import * as DocumentPicker from 'expo-document-picker';
import { useState } from 'react';
import { ActivityIndicator } from 'react-native';

import { CButton, CText } from '@/components/atoms';
import { XStack, YStack } from 'tamagui';
import { useCreateDocument } from '@/hooks/useCreateDocument';
import { useFinalizeDocument } from '@/hooks/useFinalizeDocument';
import { useUploadDocumentFile } from '@/hooks/useUploadDocumentFile';
import { Trash } from '@tamagui/lucide-icons-2';

export default function UploadScreen() {
  const [selectedFiles, setSelectedFiles] = useState<DocumentPicker.DocumentPickerAsset[]>([]);
  const { mutateAsync: createDocumentAsync, isPending: isCreating } = useCreateDocument();
  const { mutateAsync: finalizeDocumentAsync, isPending: isFinalizing } = useFinalizeDocument();
  const { uploadDocumentFileAsync, isUploading } = useUploadDocumentFile();
  const isBusy = isCreating || isUploading || isFinalizing;

  const formatSize = (bytes?: number) => {
    if (!bytes) return '0 MB';
    const mb = bytes / 1024 / 1024;
    return `${mb.toFixed(2)} MB`;
  };

  const handlePickFiles = async () => {
    const pickerResult = await DocumentPicker.getDocumentAsync({
      type: ['application/pdf', 'image/*'],
      multiple: true,
      copyToCacheDirectory: true,
    });

    if (pickerResult.canceled) return;

    setSelectedFiles(pickerResult.assets);
  };

  const handleRemoveFile = (uri: string) => {
    setSelectedFiles((current) => current.filter((file) => file.uri !== uri));
  };

  const handleStartUpload = async () => {
    if (selectedFiles.length === 0) return;

    try {
      const fileRequests = selectedFiles.map((file, index) => ({
        asset: file,
        fileName: file.name ?? `upload_file_${index + 1}`,
        contentType: file.mimeType || 'application/octet-stream',
        sizeBytes: file.size ?? 0,
      }));

      const createResponse = await createDocumentAsync({
        domain: 'medical',
        title: 'Document upload',
        files: fileRequests.map((file) => ({
          file_name: file.fileName,
          content_type: file.contentType,
          size_bytes: file.sizeBytes,
        })),
      });

      for (const file of createResponse.files) {
        const matchedFile = fileRequests.find((entry) => entry.fileName === file.file_name);
        if (!matchedFile) {
          throw new Error(`No local file found for ${file.file_name}`);
        }

        await uploadDocumentFileAsync({
          uri: matchedFile.asset.uri,
          contentType: file.content_type,
          uploadUrl: file.upload_url,
          uploadHeaders: file.upload_headers,
        });
      }

      await finalizeDocumentAsync({ documentId: createResponse.document_id });

      setSelectedFiles([]);
      alert('all files have been uploaded successfully');
      // router.navigate to documents
    } catch (error) {
      alert('an error occured: ' + String(error));
    }
  };

  return (
    <YStack flex={1} px={20} py={24} gap={20}>
      <YStack gap={8}>
        <CText variant="h2">Upload documents</CText>
        <CText variant="body">Select PDFs or images and upload them securely to your workspace.</CText>
      </YStack>

      <YStack gap={16} px={16} py={18}>
        <XStack items="center" justify="space-between">
          <YStack gap={4}>
            <CText variant="lead">Files</CText>
            <CText variant="caption">{selectedFiles.length === 0 ? 'No files selected yet' : `${selectedFiles.length} file${selectedFiles.length > 1 ? 's' : ''} ready`}</CText>
          </YStack>

          <CButton emphasis="high" onPress={handlePickFiles} disabled={isBusy}>
            Choose files
          </CButton>
        </XStack>

        <YStack gap={12}>
          {selectedFiles.map((file, index) => (
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
                <CButton icon={Trash} onPress={() => handleRemoveFile(file.uri)} disabled={isBusy}></CButton>
              </XStack>
            </XStack>
          ))}
        </YStack>
      </YStack>

      <YStack gap={12}>
        {isBusy && (
          <XStack items="center" gap={10} px={14} py={12}>
            <ActivityIndicator size="small" />
            <CText variant="body" color="#111111">
              Upload in progress...
            </CText>
          </XStack>
        )}

        {selectedFiles.length > 0 && (
          <CButton emphasis="high" fullWidth onPress={handleStartUpload} disabled={isBusy}>
            {isBusy ? `Uploading... ` : 'Start upload'}
          </CButton>
        )}
      </YStack>
    </YStack>
  );
}
