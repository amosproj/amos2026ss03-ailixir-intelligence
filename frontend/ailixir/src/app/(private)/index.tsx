import { Link } from 'expo-router';

import { CText } from '@/components/atoms';

export default function HomeScreen() {
  return (
    <>
      <CText fontSize={40}>Welcome to Ailixir!</CText>

      <Link href="/documents/" asChild>
        <CText>Go to Documents</CText>
      </Link>
      <Link href="/chats/" asChild>
        <CText>Chats</CText>
      </Link>
    </>
  );
}
