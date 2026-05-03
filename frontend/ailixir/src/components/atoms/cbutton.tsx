import { Button, styled } from 'tamagui';

export const CButton = styled(Button, {
  bg: 'transparent',
  chromeless: 'all',
  pressStyle: {
    opacity: 0.7,
  },
  variants: {
    theme: {
      green: {
        backgroundColor: 'green',
        color: 'white',
      },
    },
    iconButton: {
      true: {
        items: 'center',
        gap: 8,
      },
    },
    emphasis: {
      high: {
        backgroundColor: '#E25353',
        borderRadius: 999,
        color: 'white',
        pressStyle: {
          backgroundColor: '#E25353',
        },
      },
      medium: {},
      low: {},
    },
  } as const,
});

export type CButtonProps = React.ComponentProps<typeof CButton>;
