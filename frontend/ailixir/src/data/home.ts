import type { IconProps } from '@tamagui/helpers-icon';
import type { ComponentType } from 'react';

import { File, Plus } from '@tamagui/lucide-icons-2';

type IconComponent = ComponentType<IconProps>;

export type QuickAction = {
  title: string;
  subtitle: string;
  href: '/chats' | '/documents';
  icon: IconComponent;
  iconSize: number;
  iconStrokeWidth: number;
  iconBackground: '$blue' | '$darkblue';
};

export type RecentChat = {
  id: string;
  title: string;
  timeAgo: string;
};

export const quickActions: QuickAction[] = [
  {
    title: 'New Chat',
    subtitle: 'Start now',
    href: '/chats',
    icon: Plus,
    iconSize: 36,
    iconStrokeWidth: 2.8,
    iconBackground: '$darkblue',
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

export const recentChats: RecentChat[] = [
  { id: 'lab-reports', title: 'Lab Reports Summary', timeAgo: '2d ago' },
  { id: 'blood-results', title: 'Blood Results Review', timeAgo: '3d ago' },
  { id: 'invoices', title: 'Invoice Reconciliation', timeAgo: '5d ago' },
  { id: 'timesheets-expenses', title: 'Timesheets and Expenses', timeAgo: '1w ago' },
];
