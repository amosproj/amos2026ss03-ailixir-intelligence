import { CButton, CText } from '@/components/atoms';
import { showOcrTextAtom } from '@/state/debug';
import { useAtom } from 'jotai';
import React, { useState, useEffect } from 'react';
import { getAuth, signOut } from 'firebase/auth';
import { Switch, XStack, YStack } from 'tamagui';

export default function SettingsScreen() {
  const auth = getAuth();
  const user = auth.currentUser;
  const email = user?.email || 'No email available';
  const [token, setToken] = useState<string | null>(null);
  const [showOcrText, setShowOcrText] = useAtom(showOcrTextAtom);

  useEffect(() => {
    const fetchToken = async () => {
      if (user) {
        try {
          const idToken = await user.getIdToken();
          setToken(idToken);
          console.log('Token:', token);
        } catch (error) {
          console.error('Error accessing the Token:', error);
        }
      }
    };

    fetchToken();
  }, [user, token]);

  return (
    <YStack flex={1} bg="$background" px={16} pt={16} pb={18} justify="space-between">
      <YStack gap={14}>
        <YStack bg="$lightgray" p={16} gap={12} style={{ borderRadius: 24 }}>
          <YStack gap={2}>
            <CText variant="caption" color="$gray">
              Email
            </CText>
            <CText variant="body" color="$black">
              {email}
            </CText>
          </YStack>
        </YStack>

        {/*
          Debug section: surfaces internal toggles that aren't part of the
          customer-facing demo. Off by default; the user explicitly opts in
          per device, with the choice persisted across app restarts.
        */}
        <YStack bg="$lightgray" p={16} gap={12} style={{ borderRadius: 24 }}>
          <CText variant="caption" color="$gray">
            Debug
          </CText>
          <XStack items="center" justify="space-between" gap={12}>
            <YStack flex={1} gap={2}>
              <CText variant="body" color="$black">
                Show OCR text
              </CText>
              <CText variant="caption" color="$gray">
                Display the raw text extracted from a document on its detail screen. Useful for verifying OCR quality.
              </CText>
            </YStack>
            <Switch size="$3" checked={showOcrText} onCheckedChange={setShowOcrText} accessibilityLabel="Show OCR text on document detail screen">
              <Switch.Thumb animation="quick" />
            </Switch>
          </XStack>
        </YStack>
      </YStack>

      <XStack justify="center" pb={8}>
        <CButton
          emphasis="high"
          onPress={() => signOut(auth)}
          px={28}
          style={{ minWidth: 220, maxWidth: 320, width: '75%', shadowColor: '#00000020', shadowOffset: { width: 0, height: 10 }, shadowOpacity: 0.2, shadowRadius: 14, elevation: 6 }}>
          Log Out
        </CButton>
      </XStack>
    </YStack>
  );
}
