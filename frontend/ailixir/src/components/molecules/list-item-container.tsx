import { Link, type Href } from 'expo-router';

import { XStack } from 'tamagui';

type ListItemContainerProps = {
  href: Href;
  children: React.ReactNode;
};

export function ListItemContainer({ href, children }: ListItemContainerProps) {
  return (
    <Link href={href} asChild>
      <XStack items="center" justify="space-between" bg="$lightgray" px={18} py={18} gap={10} style={{ borderRadius: 24 }}>
        {children}
      </XStack>
    </Link>
  );
}
