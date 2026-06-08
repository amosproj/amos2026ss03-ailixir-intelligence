import { CText } from '@/components/atoms';
import { Link } from 'expo-router';

import React from 'react';

export default function ChatsScreen() {
  return (
    <Link href="/(private)/chats/id">
      <CText>Chats Overview (if needed)</CText>
    </Link>
  );
}
