import { Link } from 'expo-router';

import { CButton, CText } from '@/components/atoms';
import { getAuth } from 'firebase/auth';
import { YStack } from 'tamagui';
import { File, Bubbles, Settings } from '@tamagui/lucide-icons-2';

export default function HomeScreen() {
  const auth = getAuth();
  const user = auth.currentUser;
  return (
    <YStack width="100%" height="100%" justify="center" items="center" gap={10}>
      <CText variant="h1">Hello {user?.email}</CText>
      <CText variant="h2">Welcome to Ailixir!</CText>

      <Link href="/documents" asChild>
        <CButton iconButton icon={File} bg="$background06">
          Documents
        </CButton>
      </Link>
      <Link href="/chats" asChild>
        <CButton iconButton icon={Bubbles} bg="$background06">
          Chats
        </CButton>
      </Link>

      <Link href="/settings" asChild>
        <CButton iconButton icon={Settings} bg="$background06">
          Settings
        </CButton>
      </Link>
    </YStack>
  );
}
