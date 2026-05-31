import { Link, type Href } from 'expo-router';

import { CText } from '@/components/atoms';
import { XStack, YStack } from 'tamagui';

type ListItemContainerProps = {
  href: Href;
  children: React.ReactNode;
};

type ListItemContentProps = {
  href: Href;
  icon: React.ReactNode;
  title: string;
  subtitle?: string;
  meta?: React.ReactNode;
  contentAccessory?: React.ReactNode;
  endAdornment?: React.ReactNode;
};

export function ListItemContainer({ href, children }: ListItemContainerProps) {
  return (
    <Link href={href} asChild>
      <XStack items="center" justify="space-between" bg="$white02" px={18} py={18} gap={10}>
        {children}
      </XStack>
    </Link>
  );
}

export function ListItemContent({ href, icon, title, subtitle, meta, contentAccessory, endAdornment }: ListItemContentProps) {
  return (
    <ListItemContainer href={href}>
      <XStack items="center" gap={14} flex={1}>
        {icon}
        <YStack gap={2} flex={1}>
          <CText variant="lead" numberOfLines={1}>
            {title}
          </CText>
          {subtitle && <CText variant="body">{subtitle}</CText>}
          {meta}
        </YStack>
        {contentAccessory}
      </XStack>
      {endAdornment}
    </ListItemContainer>
  );
}
