import { CButton, CText } from '@/components/atoms';
import { ChevronRight, File, Upload } from '@tamagui/lucide-icons-2';
import React from 'react';
import { XStack, YStack } from 'tamagui';

export default function DocumentsScreen() {
  return (
    <YStack flex={1} backgroundColor="#F2F2F2" paddingTop={10} paddingHorizontal={16}>
      <YStack marginTop={28} gap={4}>
        <CText fontSize={16} color="#7A7A7A">
          6 Documents
        </CText>
        <CText fontSize={16} color="#7A7A7A">
          2 Uploads pending
        </CText>
      </YStack>

      <XStack marginTop={170} justify="flex-end" alignItems="center" gap={16}>
        <CButton iconButton icon={Upload} color="#202020" fontSize={18}>
          upload
        </CButton>
        <CButton iconButton icon={ChevronRight} color="#E8E6FF" fontSize={18} fontWeight="500" backgroundColor="#7B74F7" borderRadius={999} paddingHorizontal={18} paddingVertical={10}>
          scan
        </CButton>
      </XStack>

      <XStack marginTop={56} justify="space-between" alignItems="center" paddingHorizontal={4}>
        <CText fontSize={16} color="#E25353" fontWeight="500">
          ALL
        </CText>
        <CText fontSize={16} color="#4B4B4B" letterSpacing={0.2}>
          MEDICAL REPORTS
        </CText>
        <CText fontSize={16} color="#4B4B4B" letterSpacing={0.2}>
          LAB RESULTS
        </CText>
      </XStack>

      <XStack marginTop={20} alignItems="center" justify="space-between" paddingHorizontal={20} paddingVertical={16} borderRadius={8} backgroundColor="#ECECEC">
        <XStack alignItems="center" gap={14} flex={1}>
          <File size={34} color="#111111" />
          <YStack>
            <CText fontSize={24} fontWeight="5s00" color="#111111">
              Lorem Ipsum
            </CText>
            <CText fontSize={16} color="#7B7B7B">
              12.03.2026 425kb
            </CText>
            <CText marginTop={4} fontSize={16} color="#6F65F5" fontWeight="600">
              #Lab Result
            </CText>
          </YStack>
        </XStack>

        <ChevronRight size={34} color="#111111" />
      </XStack>
    </YStack>
  );
}
