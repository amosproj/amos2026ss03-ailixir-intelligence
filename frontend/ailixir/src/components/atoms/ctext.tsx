import { styled, Text } from 'tamagui';

export const CText = styled(Text, {
  variants: {} as const,
});

export type CTextProps = React.ComponentProps<typeof CText>;
