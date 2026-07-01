import type { IconProps } from '@tamagui/helpers-icon';
import type { ComponentType } from 'react';

import { File, MessageCircle } from '@tamagui/lucide-icons-2';

type IconComponent = ComponentType<IconProps>;

export type QuickAction = {
  title: string;
  subtitle: string;
  href: '/chats' | '/documents';
  icon: IconComponent;
  iconSize: number;
  iconStrokeWidth: number;
  iconBackground: any;
  onPress?: () => void;
};

export type RecentChat = {
  id: string;
  title: string;
  // Preview of the last message, shown under the title in the chat row.
  preview: string;
  // Short relative timestamp shown on the right (e.g. "4:05 PM", "Yesterday",
  // "May 21"). Built from the chat's last-activity time.
  timeLabel: string;
};

export const quickActions: QuickAction[] = [
  {
    title: 'New Chat',
    subtitle: 'Start now',
    href: '/chats',
    icon: MessageCircle,
    iconSize: 30,
    iconStrokeWidth: 2.8,
    iconBackground: '$accent10',
  },
  {
    title: 'Documents',
    subtitle: 'Browse files',
    href: '/documents',
    icon: File,
    iconSize: 30,
    iconStrokeWidth: 2.2,
    iconBackground: '$blue',
  },
];
