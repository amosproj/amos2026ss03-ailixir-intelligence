import * as DocumentPicker from 'expo-document-picker';
import { useState } from 'react';

import { YStack } from 'tamagui';
import { useQueryClient } from '@tanstack/react-query';
import { useCreateDocument } from '@/hooks/useCreateDocument';
import { useFinalizeDocument } from '@/hooks/useFinalizeDocument';
import { useUploadDocumentFile } from '@/hooks/useUploadDocumentFile';
import { getFileBaseName } from '@/utils/format';
import { resolveDocumentContentType } from '@/utils/documents';
import { router } from 'expo-router';
import { UploadActions, UploadFilesPanel, UploadHeader } from '@/components/molecules';

export default function UploadScreen() {
  const [selectedFiles, setSelectedFiles] = useState<DocumentPicker.DocumentPickerAsset[]>([]);
  const queryClient = useQueryClient();
  const { mutateAsync: createDocumentAsync, isPending: isCreating } = useCreateDocument();
  const { mutateAsync: finalizeDocumentAsync, isPending: isFinalizing } = useFinalizeDocument();
  const { uploadDocumentFileAsync, isUploading } = useUploadDocumentFile();
  const isBusy = isCreating || isUploading || isFinalizing;

  const handlePickFiles = async () => {
    const pickerResult = await DocumentPicker.getDocumentAsync({
      type: ['application/pdf', 'image/*'],
      multiple: true,
      copyToCacheDirectory: true,
    });

    if (pickerResult.canceled) return;

    const acceptedFiles = pickerResult.assets.filter((file) => Boolean(resolveDocumentContentType(file.name ?? '', file.mimeType)));
    const rejectedCount = pickerResult.assets.length - acceptedFiles.length;

    setSelectedFiles(acceptedFiles);

    if (rejectedCount > 0) {
      alert(`Skipped ${rejectedCount} file(s). Allowed types: PDF, PNG, JPEG.`);
    }
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
        contentType: resolveDocumentContentType(file.name ?? '', file.mimeType),
        sizeBytes: file.size ?? 0,
      }));

      const invalidFiles = fileRequests.filter((file) => !file.contentType);
      if (invalidFiles.length > 0) {
        alert('Only PDF, PNG, or JPEG files can be uploaded.');
        return;
      }

      const title = getFileBaseName(fileRequests[0]?.fileName);

      const createResponse = await createDocumentAsync({
        domain: 'medical',
        title,
        files: fileRequests.map((file) => ({
          file_name: file.fileName,
          content_type: file.contentType ?? 'application/octet-stream',
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
      queryClient.invalidateQueries({ queryKey: ['documents'] });
      alert('all files have been uploaded successfully');
      router.back();
    } catch (error) {
      alert('an error occured: ' + String(error));
    }
  };

  return (
    <YStack flex={1} px={20} py={24} gap={20}>
      <UploadHeader title="Upload documents" subtitle="Select PDFs or images and upload them securely to your workspace." />
      <UploadFilesPanel files={selectedFiles} isBusy={isBusy} onPickFiles={handlePickFiles} onRemoveFile={handleRemoveFile} />
      <UploadActions isBusy={isBusy} hasFiles={selectedFiles.length > 0} onStartUpload={handleStartUpload} />
    </YStack>
  );
}
