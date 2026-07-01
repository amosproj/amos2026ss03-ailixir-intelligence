import { CButton, CText } from '@/components/atoms';
import { ConversationProvider, useConversationControls, useConversationStatus, useConversationMode } from '@elevenlabs/react-native';
import { getFunctions, httpsCallable } from 'firebase/functions';
import React, { useEffect, useState } from 'react';
import { Alert, Platform, PermissionsAndroid } from 'react-native';
import { ScrollView, XStack, YStack } from 'tamagui';

const STATUS_LABELS: Record<string, string> = {
  disconnected: 'Disconnected',
  connecting: 'Connecting...',
  connected: 'Connected',
  disconnecting: 'Disconnecting...',
};

function STTContent() {
  const { startSession, endSession } = useConversationControls();
  const { status, message } = useConversationStatus();
  const { isSpeaking, isListening } = useConversationMode();
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    console.log(`[STT] Status changed: ${status}`);
  }, [status]);

  const requestMicrophonePermission = async () => {
    if (Platform.OS === 'android') {
      try {
        const granted = await PermissionsAndroid.request(PermissionsAndroid.PERMISSIONS.RECORD_AUDIO, {
          title: 'Microphone Permission',
          message: 'This app needs microphone access to enable voice conversations.',
          buttonNeutral: 'Ask Me Later',
          buttonNegative: 'Cancel',
          buttonPositive: 'OK',
        });
        return granted === PermissionsAndroid.RESULTS.GRANTED;
      } catch {
        return false;
      }
    }
    return true;
  };

  const handleToggle = async () => {
    setError(null);

    if (status === 'connected' || status === 'connecting') {
      console.log('[STT] Ending session');
      endSession();
      return;
    }

    const hasPermission = await requestMicrophonePermission();
    if (!hasPermission) {
      Alert.alert('Permission Denied', 'Microphone permission is required for voice conversations.');
      return;
    }

    setIsLoading(true);
    try {
      console.log('[STT] Fetching signed URL...');
      const functions = getFunctions();
      const getSignedUrlFn = httpsCallable(functions, 'signedUrl');
      const result = await getSignedUrlFn();
      const { signedUrl } = result.data as { signedUrl: string };
      console.log('[STT] Signed URL retrieved successfully');

      console.log('[STT] Starting session...');
      await startSession({ signedUrl });
      console.log('[STT] Session started');
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to start conversation';
      console.error('[STT] Error:', msg);
      setError(msg);
    } finally {
      setIsLoading(false);
    }
  };

  const isActive = status === 'connected' || status === 'connecting';

  return (
    <ScrollView flex={1} bg="$background">
      <YStack flex={1} px={16} pt={16} pb={18} gap={24}>
        <YStack bg="$lightgray" p={16} gap={12} style={{ borderRadius: 24 }}>
          <XStack items="center" justify="space-between">
            <CText variant="caption" color="$gray">
              Status
            </CText>
            <CText variant="body" bold color="$black">
              {STATUS_LABELS[status] || status}
            </CText>
          </XStack>

          {status === 'connected' && (
            <XStack items="center" justify="space-between">
              <CText variant="caption" color="$gray">
                Mode
              </CText>
              <CText variant="body" bold color="$black">
                {isSpeaking ? 'Speaking' : isListening ? 'Listening' : 'Idle'}
              </CText>
            </XStack>
          )}

          {message ? (
            <YStack gap={4}>
              <CText variant="caption" color="$gray">
                Last message
              </CText>
              <CText variant="body" color="$black" numberOfLines={2}>
                {message}
              </CText>
            </YStack>
          ) : null}
        </YStack>

        <XStack justify="center" pt={20}>
          <CButton emphasis="high" onPress={handleToggle} disabled={isLoading} opacity={isLoading ? 0.6 : 1} px={28} py={14} style={{ minWidth: 220 }}>
            {isLoading ? 'Starting...' : isActive ? 'End Conversation' : 'Start Conversation'}
          </CButton>
        </XStack>

        {error ? (
          <XStack bg="#FEE2E2" p={12} style={{ borderRadius: 12 }} justify="center">
            <CText variant="body" color="#DC2626">
              {error}
            </CText>
          </XStack>
        ) : null}
      </YStack>
    </ScrollView>
  );
}

export default function STTScreen() {
  return (
    <ConversationProvider>
      <STTContent />
    </ConversationProvider>
  );
}
