import { styled, Text } from 'tamagui';

export const CText = styled(Text, {
  variants: {
    variant: {
      title: {
        fontSize: 28,
        fontWeight: '500',
      },
      subtitle: {
        fontSize: 20,
        fontWeight: '500',
      },
      lead: {
        fontSize: 16,
        fontWeight: '400',
      },
      body: {
        fontSize: 14,
      },
      caption: {
        fontSize: 12,
        color: '#7B7B7B',
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
