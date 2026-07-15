import { Link, type Href } from 'expo-router';
import { RectButton } from 'react-native-gesture-handler';

import { CText } from '@/components/atoms';
import { XStack, YStack } from 'tamagui';

type ListItemContainerProps = {
  href?: Href;
  onPress?: () => void;
  children: React.ReactNode;
};

type ListItemContentProps = {
  href?: Href;
  onPress?: () => void;
  icon: React.ReactNode;
  title: string;
  subtitle?: string;
  meta?: React.ReactNode;
  contentAccessory?: React.ReactNode;
  endAdornment?: React.ReactNode;
};

export function ListItemContainer({ href, onPress, children }: ListItemContainerProps) {
  const content = (
    <XStack items="center" justify="space-between" bg="$accent12" px={18} py={18} gap={10}>
      {children}
    </XStack>
  );

  if (onPress) {
    return <RectButton onPress={onPress}>{content}</RectButton>;
  }

  if (!href) {
    return content;
  }

  return (
    <Link href={href} asChild>
      {content}
    </Link>
  );
}

export function ListItemContent({ href, onPress, icon, title, subtitle, meta, contentAccessory, endAdornment }: ListItemContentProps) {
  return (
    <ListItemContainer href={href} onPress={onPress}>
      <XStack items="center" gap={14} flex={1}>
        {icon}
        <YStack gap={2} flex={1}>
          <CText variant="lead" numberOfLines={1}>
            {title}
          </CText>
          {/* Secondary text (chat preview, document metadata): muted and
              clipped to one line so long values never wrap the row. */}
          {subtitle && (
            <CText variant="body" color="$accent5" numberOfLines={1}>
              {subtitle}
            </CText>
          )}
          {meta}
        </YStack>
        {contentAccessory}
      </XStack>
      {endAdornment}
    </ListItemContainer>
  );
}
