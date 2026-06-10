import { CText } from '@/components/atoms';
import { Image } from 'expo-image';
import { FileText } from '@tamagui/lucide-icons-2';
import React, { useState } from 'react';
import { Linking, Pressable } from 'react-native';
import { ScrollView, XStack, YStack } from 'tamagui';

export type DocumentPage = {
  id: string;
  pageNumber?: number;
  thumbnail?: string;
  fileName?: string;
  contentType?: string;
  downloadUrl?: string;
};

export type DocumentPageSourceFile = {
  file_id: string;
  file_name: string;
  content_type: string;
  download_url: string;
};

export type DocumentPageThumbnailProps = {
  page: DocumentPage;
};

export type DocumentPagesThumbnailsProps = {
  files: DocumentPageSourceFile[];
};

export function DocumentPagesThumbnails({ files }: DocumentPagesThumbnailsProps) {
  return (
    <ScrollView horizontal showsHorizontalScrollIndicator={false}>
      <XStack gap={12} pb={8}>
        {files.map((file) => (
          <DocumentPageThumbnail
            key={file.file_id}
            page={{
              id: file.file_id,
              pageNumber: 1,
              fileName: file.file_name,
              contentType: file.content_type,
              downloadUrl: file.download_url,
            }}
          />
        ))}
      </XStack>
    </ScrollView>
  );
}

export function DocumentPageThumbnail({ page }: DocumentPageThumbnailProps) {
  const [imageFailed, setImageFailed] = useState(false);
  const isImage = Boolean(page.contentType?.startsWith('image/'));
  const showImagePreview = isImage && Boolean(page.downloadUrl) && !imageFailed;

  return (
    <Pressable onPress={() => page.downloadUrl && Linking.openURL(page.downloadUrl)}>
      <YStack width={136} gap={8}>
        <XStack height={180} bg="#FAFAFA" borderWidth={1} borderColor="#D8D8D8" items="center" justify="center" style={{ borderRadius: 16 }}>
          {showImagePreview ? (
            <Image source={{ uri: page.downloadUrl }} style={{ width: '100%', height: '100%', borderRadius: 16 }} contentFit="cover" transition={150} onError={() => setImageFailed(true)} />
          ) : (
            <YStack items="center" gap={10} px={10}>
              <FileText size={36} color="#4F4F4F" />
              <CText variant="caption" color="#4F4F4F" style={{ textAlign: 'center' }}>
                {page.contentType === 'application/pdf' ? 'PDF document' : 'Preview unavailable'}
              </CText>
            </YStack>
          )}
        </XStack>

        <CText variant="caption" bold>
          {page.contentType === 'application/pdf' ? 'PDF' : 'Image'}
        </CText>

        {!!page.fileName && (
          <CText variant="caption" color="$color9" numberOfLines={1}>
            {page.fileName}
          </CText>
        )}
      </YStack>
    </Pressable>
  );
}
