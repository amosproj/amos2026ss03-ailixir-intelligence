import { CButton, CText } from '@/components/atoms';
import { CameraButton } from '@/components/molecules';
import { useCreateDocument } from '@/hooks/useCreateDocument';
import { useFinalizeDocument } from '@/hooks/useFinalizeDocument';
import { useUploadDocumentFile } from '@/hooks/useUploadDocumentFile';
import { resolveDocumentContentType } from '@/utils/documents';
import { Camera, Trash2, Upload } from '@tamagui/lucide-icons-2';
import * as ImagePicker from 'expo-image-picker';
import { Image } from 'expo-image';
import React, { useState } from 'react';
import { Modal, useWindowDimensions, Pressable } from 'react-native';
import { ScrollView, XStack, YStack } from 'tamagui';
import { useQueryClient } from '@tanstack/react-query';
import { router } from 'expo-router';

export default function CaptureScreen() {
  const [pages, setPages] = useState<ImagePicker.ImagePickerAsset[]>([]);
  const { height: windowHeight, width: windowWidth } = useWindowDimensions();
  const queryClient = useQueryClient();
  const { mutateAsync: createDocumentAsync, isPending: isCreating } = useCreateDocument();
  const { mutateAsync: finalizeDocumentAsync, isPending: isFinalizing } = useFinalizeDocument();
  const { uploadDocumentFileAsync, isUploading } = useUploadDocumentFile();
  const [isScanning, setIsScanning] = useState(false);

  const handleAddPage = (photo: ImagePicker.ImagePickerAsset) => {
    setPages((prev) => [...prev, photo]);
  };

  const handleDeletePage = (index: number) => {
    setPages((prev) => prev.filter((_, i) => i !== index));
  };

  const handleUpload = async () => {
    if (pages.length === 0) return;
    setIsScanning(true);

    try {
      const fileRequests = pages.map((page, index) => ({
        asset: page,
        fileName: `page_${index + 1}.jpg`,
        contentType: resolveDocumentContentType(page.uri) || 'image/jpeg',
        sizeBytes: page.fileSize || 0,
      }));

      const createResponse = await createDocumentAsync({
        domain: 'medical',
        title: `Document - ${new Date().toLocaleDateString()}`,
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

      setPages([]);
      queryClient.invalidateQueries({ queryKey: ['documents'] });
      alert('Document uploaded successfully');
      router.back();
    } catch (error) {
      alert('An error occurred: ' + String(error));
    } finally {
      setIsScanning(false);
    }
  };

  return (
    <YStack flex={1} bg="$accent12">
      <Modal visible={isScanning} transparent animationType="fade">
        <YStack flex={1} bg="rgba(0, 0, 0, 0.5)" items="center" justify="center" gap={12}>
          <CText variant="h2" color="$white">
            {isCreating && 'Creating document...'}
            {isUploading && 'Uploading pages...'}
            {isFinalizing && 'Finalizing document...'}
          </CText>
        </YStack>
      </Modal>
      {/* Header with Upload Button */}
      <XStack px={16} py={12} items="center" justify="space-between">
        <YStack>
          <CText variant="h2">Pages</CText>
          <CText variant="caption">
            {pages.length} page{pages.length !== 1 ? 's' : ''} scanned
          </CText>
        </YStack>
        <CButton icon={Upload} onPress={handleUpload}>
          <CText variant="lead">Upload</CText>
        </CButton>
      </XStack>

      {/* Main Content */}
      {pages.length === 0 ? (
        // Empty State
        <YStack flex={1} items="center" justify="center" gap={12}>
          <CText variant="h2">No pages yet</CText>
          <CameraButton emphasis="high" defaultText="Add Page" loadingText="Scanning..." onPhoto={handleAddPage} />
        </YStack>
      ) : (
        // Grid Layout
        <ScrollView showsVerticalScrollIndicator={false} px={16} pb={80}>
          <YStack width="100%" gap={12} py={12} style={{ flexDirection: 'column', display: 'flex', justifyContent: 'center', height: '100%' }}>
            {/* Render pages in 2-column grid with add page button at the end */}
            {pages.map((page, index) => (
              <YStack key={index} flex={1} gap={8}>
                {/* Thumbnail Container */}
                <YStack style={{ margin: 'auto', flex: 1, position: 'relative', width: '50%', height: 0.3 * windowHeight, overflow: 'hidden' }}>
                  <Image source={{ uri: page.uri }} style={{ width: undefined, height: undefined, flex: 1 }} contentFit="contain"></Image>
                </YStack>
                <Pressable
                  onPress={() => handleDeletePage(index)}
                  style={{
                    position: 'absolute',
                    top: 8,
                    left: windowWidth * 0.5 - 28, // Center the button horizontally over the thumbnail
                    zIndex: 10,
                    backgroundColor: 'rgba(0, 0, 0, 0.5)',
                    borderRadius: 20,
                    padding: 6,
                  }}>
                  <Trash2 size={16} color="white" />
                </Pressable>

                {/* Page Number */}
                <CText variant="caption" bold style={{ textAlign: 'center' }}>
                  Page {index + 1}
                </CText>
              </YStack>
            ))}
          </YStack>
        </ScrollView>
      )}

      {/* Floating Action Button - Lower Right */}
      <CameraButton
        defaultText=""
        loadingText=""
        position="absolute"
        style={{ bottom: 24, right: 24 }}
        emphasis="high"
        onPhoto={handleAddPage}
        icon={Camera}
        circular
        accessibilityLabel="Add Page"></CameraButton>
    </YStack>
  );
}
