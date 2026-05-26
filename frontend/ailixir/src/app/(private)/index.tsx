import { Link } from 'expo-router';
import { getAuth } from 'firebase/auth';

import { CButton, CText } from '@/components/atoms';
import { File, MessageCircle, Plus } from '@tamagui/lucide-icons-2';
import { ScrollView, XStack, YStack } from 'tamagui';

type IconComponent = typeof Plus;

type QuickAction = {
  title: string;
  subtitle: string;
  href: '/chats' | '/documents';
  icon: IconComponent;
  iconSize: number;
  iconStrokeWidth: number;
  iconBackground: '$blue' | '$darkblue';
};

const quickActions: QuickAction[] = [
  {
    title: 'New Chat',
    subtitle: 'Start now',
    href: '/chats' as const,
    icon: Plus,
    iconSize: 36,
    iconStrokeWidth: 2.8,
    iconBackground: '$darkblue',
  },
  {
    title: 'Documents',
    subtitle: 'Browse files',
    href: '/documents' as const,
    icon: File,
    iconSize: 30,
    iconStrokeWidth: 2.2,
    iconBackground: '$blue',
  },
];

const recentChats = [
  { id: 'q1-report', title: 'Q1 Financial Report Analysis', timeAgo: '2d ago' },
  { id: 'proposal', title: 'Project Proposal Overview', timeAgo: '3d ago' },
  { id: 'marketing-2026', title: 'Marketing Strategy 2026', timeAgo: '5d ago' },
];

export default function HomeScreen() {
  const auth = getAuth();
  const displayName = auth.currentUser?.displayName?.trim();

  return (
    <ScrollView flex={1} bg="$background">
      <YStack gap={14} px={16} py={16}>
        <YStack px={6} pb={4}>
          <CText variant="h2" color="$black">
            Welcome back, {displayName || 'Tim'}
          </CText>
          <CText variant="lead" color="$gray" mt={4}>
            What do you want to explore today?
          </CText>
        </YStack>

        <XStack gap={12} flexWrap="wrap">
          {quickActions.map((action) => (
            <Link key={action.title} href={action.href} asChild>
              <YStack flex={1} gap={14} p={20} bg="$lightgray" items="center" justify="center" style={{ minWidth: 160, minHeight: 180, borderRadius: 30 }}>
                <YStack width={64} height={64} items="center" justify="center" bg={action.iconBackground} style={{ borderRadius: 20 }}>
                  <action.icon size={action.iconSize} color="white" strokeWidth={action.iconStrokeWidth} />
                </YStack>
                <YStack gap={4} items="center">
                  <CText variant="h2" color="$black">
                    {action.title}
                  </CText>
                  <CText variant="body" color="$gray">
                    {action.subtitle}
                  </CText>
                </YStack>
              </YStack>
            </Link>
          ))}
        </XStack>

        <XStack justify="space-between" items="center" px={6} mt={10}>
          <CText variant="h1" color="$black">
            Recent Chats
          </CText>
          <Link href="/chats" asChild>
            <CButton p={0}>
              <CText variant="lead" color="$blue" bold>
                View All
              </CText>
            </CButton>
          </Link>
        </XStack>

        <YStack gap={10}>
          {recentChats.map((chat) => (
            <Link key={chat.id} href="/chats" asChild>
              <XStack items="center" justify="space-between" bg="$lightgray" px={18} py={18} gap={10} style={{ borderRadius: 24 }}>
                <YStack flex={1} gap={2}>
                  <CText variant="lead" color="$black" numberOfLines={1}>
                    {chat.title}
                  </CText>
                  <CText variant="body" color="$gray">
                    {chat.timeAgo}
                  </CText>
                </YStack>
                <MessageCircle size={22} color="#847EF3" />
              </XStack>
            </Link>
          ))}
        </YStack>
      </YStack>
    </ScrollView>
  );
}
