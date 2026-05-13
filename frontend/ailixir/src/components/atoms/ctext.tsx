import { styled, Text } from 'tamagui';
import { typography } from '../../constants/typography';

export const CText = styled(Text, {
  fontFamily: '$body',
  variants: {
    variant: {
      h1: {
        ...typography.h1,
      },
      h2: {
        ...typography.h2,
      },
      title: {
        ...typography.h1,
      },
      subtitle: {
        ...typography.h2,
      },
      lead: {
        ...typography.lead,
      },
      body: {
        ...typography.body,
      },
      caption: {
        ...typography.caption,
      },
    },
    bold: {
      true: {
        fontWeight: '600',
      },
    },
    tag: {
      true: {
        color: '#6F65F5',
        fontWeight: '500',
      },
    },
  } as const,
});

export type CTextProps = React.ComponentProps<typeof CText>;
