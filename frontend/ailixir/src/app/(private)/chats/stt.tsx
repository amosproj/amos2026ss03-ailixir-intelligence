import { CButton, CText } from '@/components/atoms';
import { VoicePulseCircle } from '@/components/molecules';
import { ConversationProvider, useConversationControls, useConversationStatus, useConversationMode } from '@elevenlabs/react-native';
import { AudioSession } from '@livekit/react-native';
import { requestRecordingPermissionsAsync } from 'expo-audio';
import { useLocalSearchParams } from 'expo-router';
import { getFunctions, httpsCallable } from 'firebase/functions';
import { getAuth } from 'firebase/auth';
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Alert, Platform, PermissionsAndroid, View } from 'react-native';
import { ScrollView, XStack, YStack } from 'tamagui';
import { addAssistantMessage, addUserMessage } from '@/lib/chat-rtdb';

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
  const { chatId } = useLocalSearchParams<{ chatId?: string }>();
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const processedEventIdsRef = useRef<Set<number>>(new Set());

  useEffect(() => {
    return () => {
      try {
        AudioSession.stopAudioSession();
      } catch (err) {
        console.error(err);
      }
    };
  }, []);

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

    if (Platform.OS === 'ios') {
      try {
        const { granted } = await requestRecordingPermissionsAsync();
        return granted;
      } catch {
        return false;
      }
    }

    return true;
  };

  const persistVoiceTurn = useCallback(
    async (payload: { role: 'user' | 'agent'; message: string; event_id?: number }) => {
      const uid = getAuth().currentUser?.uid;
      const text = payload.message.trim();
      if (!uid || !chatId || !text) return;

      if (typeof payload.event_id === 'number') {
        if (processedEventIdsRef.current.has(payload.event_id)) return;
        processedEventIdsRef.current.add(payload.event_id);
      }

      if (payload.role === 'user') {
        await addUserMessage(uid, chatId, { content: text });
        return;
      }

      await addAssistantMessage(uid, chatId, { content: text });
    },
    [chatId],
  );

  const handleToggle = async () => {
    setError(null);

    if (status === 'connected' || status === 'connecting') {
      endSession();
      try {
        AudioSession.stopAudioSession();
      } catch (err) {
        console.error(err);
      }
      return;
    }

    const hasPermission = await requestMicrophonePermission();
    if (!hasPermission) {
      Alert.alert('Permission Denied', 'Microphone permission is required for voice conversations.');
      return;
    }

    setIsLoading(true);
    try {
      await AudioSession.configureAudio({
        android: {
          preferredOutputList: ['speaker'],
        },
        ios: {
          defaultOutput: 'speaker',
        },
      });
      await AudioSession.startAudioSession();

      const functions = getFunctions();
      const getConversationTokenFn = httpsCallable(functions, 'getWebrtcToken');
      const result = await getConversationTokenFn();
      const { token } = result.data as { token: string };

      startSession({
        conversationToken: token,
        onMessage: (payload) => {
          void persistVoiceTurn(payload);
        },
      });
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to start conversation';
      setError(msg);
      try {
        AudioSession.stopAudioSession();
      } catch (stopErr) {
        console.error(stopErr);
      }
    } finally {
      setIsLoading(false);
    }
  };

  const isActive = status === 'connected' || status === 'connecting';

  return (
    <ScrollView flex={1} bg="$background" contentContainerStyle={{ flexGrow: 1 }}>
      <YStack flex={1} px={16} pt={16} pb={18} justify="space-between">
        <YStack bg="$lightgray" p={20} gap={16} style={{ borderRadius: 24 }}>
          <XStack items="center" justify="space-between">
            <YStack gap={2}>
              <CText variant="caption" color="$gray">
                Voice Assistant Status
              </CText>
              <CText variant="body" bold color="$black">
                {STATUS_LABELS[status] || status}
              </CText>
            </YStack>
            <View
              style={{
                width: 12,
                height: 12,
                borderRadius: 6,
                backgroundColor: status === 'connected' ? '#10B981' : status === 'connecting' ? '#F59E0B' : '#9CA3AF',
              }}
            />
          </XStack>

          {status === 'connected' && (
            <XStack items="center" justify="space-between">
              <CText variant="caption" color="$gray">
                Current Mode
              </CText>
              <CText variant="body" bold color="$black">
                {isSpeaking ? 'Speaking' : isListening ? 'Listening' : 'Idle'}
              </CText>
            </XStack>
          )}

          {!isActive && (
            <CText variant="caption" color="$gray">
              Start a voice session to begin speaking with the AI assistant.
            </CText>
          )}
        </YStack>

        <YStack flex={1} items="center" justify="center" py={30}>
          <VoicePulseCircle status={status} isSpeaking={isSpeaking} isListening={isListening} isLoading={isLoading} onPress={handleToggle} />
        </YStack>

        <YStack gap={16} items="center" width="100%">
          {!chatId && (
            <XStack bg="#FEF3C7" p={12} style={{ borderRadius: 12 }} justify="center" width="100%">
              <CText variant="body" color="#92400E" style={{ textAlign: 'center' }}>
                Voice chat is not linked to a chat thread from this screen. Open Voice Mode from inside a chat to save transcript messages.
              </CText>
            </XStack>
          )}

          {message ? (
            <YStack bg="$lightgray" p={16} gap={6} style={{ borderRadius: 20, width: '100%' }}>
              <CText variant="caption" color="$gray">
                Last Message
              </CText>
              <CText variant="body" color="$black" numberOfLines={4}>
                &quot;{message}&quot;
              </CText>
            </YStack>
          ) : isActive ? (
            <CText variant="body" color="$gray" style={{ textAlign: 'center', fontStyle: 'italic' }}>
              {isSpeaking ? 'AI is speaking...' : isListening ? 'Listening to you...' : 'Listening...'}
            </CText>
          ) : null}

          {error && (
            <XStack bg="#FEE2E2" p={12} style={{ borderRadius: 12 }} justify="center" width="100%">
              <CText variant="body" color="#DC2626" style={{ textAlign: 'center' }}>
                {error}
              </CText>
            </XStack>
          )}

          <XStack justify="center" width="100%">
            <CButton
              emphasis="high"
              onPress={handleToggle}
              disabled={isLoading}
              opacity={isLoading ? 0.6 : 1}
              px={28}
              py={14}
              backgroundColor={isActive ? '#EF4444' : '$accent9'}
              style={{
                minWidth: 220,
                maxWidth: 320,
                width: '75%',
                shadowColor: isActive ? '#EF4444' : '#00000020',
                shadowOffset: { width: 0, height: 10 },
                shadowOpacity: 0.2,
                shadowRadius: 14,
                elevation: 6,
              }}>
              {isLoading ? 'Starting...' : isActive ? 'End Conversation' : 'Start Conversation'}
            </CButton>
          </XStack>
        </YStack>
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
