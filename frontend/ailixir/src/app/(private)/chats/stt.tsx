import { CButton, CText } from '@/components/atoms';
import { useScribe } from '@elevenlabs/react';
import { useQuery } from '@tanstack/react-query';
import { requestRecordingPermissionsAsync, setAudioModeAsync } from 'expo-audio';
import React, { useEffect } from 'react';
import { XStack, YStack } from 'tamagui';

/**
 * During Development: make sure that the scribe token provider is running!
 * It's shipped in the /poc/elvenlabs-token-service directory. run with `npm run dev`.
 */
const SCRIBE_TOKEN_URL = 'http://localhost:3000/scribe-token';

export default function STTScreen() {
  const scribe = useScribe({
    modelId: 'scribe_v2_realtime',
    onSessionStarted: () => console.log('Session started'),
    onPartialTranscript: (data) => {
      console.log('Partial:', data.text);
    },
    onCommittedTranscript: (data) => {
      console.log('Committed:', data.text);
    },
    onCommittedTranscriptWithTimestamps: (data) => {
      console.log('Committed with timestamps:', data.text);
      console.log('Timestamps:', data.words);
    },
    onError: (error) => {
      console.error('Scribe error:', error);
    },
  });

  const { refetch: getToken, isFetching: isTokenLoading } = useQuery({
    queryKey: ['scribe-token'],
    queryFn: async () => {
      const res = await fetch(SCRIBE_TOKEN_URL);
      if (!res.ok) throw new Error('Failed to fetch scribe token');
      return res.json() as Promise<{ token: string }>;
    },
    enabled: false,
  });

  useEffect(() => {
    return () => {
      if (scribe.isConnected) scribe.disconnect();
    };
  }, [scribe]);

  const handleStart = async () => {
    try {
      // Request Microphone Permissions
      const { granted } = await requestRecordingPermissionsAsync();
      if (!granted) {
        console.warn('Microphone permission denied');
        return;
      }

      await setAudioModeAsync({
        allowsRecording: true,
        playsInSilentMode: true,
      });

      const result = await getToken();
      const token = result.data?.token;
      if (!token) throw new Error('No token received');

      await scribe.connect({
        token,
        microphone: {
          echoCancellation: true,
          noiseSuppression: true,
        },
      });
    } catch (err) {
      console.error('Failed to start:', err);
    }
  };

  const handleStop = () => {
    scribe.disconnect();
  };

  const isBusy = isTokenLoading || scribe.status === 'connecting';
  const isActive = scribe.isConnected;

  return (
    <YStack flex={1} bg="$background">
      <CText variant="caption" mb={16}>
        Status: {scribe.status}
      </CText>

      {scribe.error && (
        <CText variant="body" color="$red10" mb={16}>
          Error: {scribe.error}
        </CText>
      )}

      <XStack gap={12} mb={24}>
        <CButton emphasis="high" onPress={handleStart} disabled={isBusy || isActive}>
          {isTokenLoading ? 'Connecting...' : 'Start Recording'}
        </CButton>
        <CButton emphasis="medium" onPress={handleStop} disabled={!isActive}>
          Stop
        </CButton>
      </XStack>
    </YStack>
  );
}
