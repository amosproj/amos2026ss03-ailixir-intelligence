import { Button, styled } from 'tamagui';

export const CButton = styled(Button, {
  chromeless: 'all',
  pressStyle: {
    opacity: 0.7,
  },
  variants: {
    theme: {
      blue: {
        backgroundColor: '$blue',
        color: 'white',
      },
    },
    iconButton: {
      true: {
        items: 'center',
        gap: 8,
      },
    },
    fullWidth: {
      true: {
        width: '100%',
      },
    },
    emphasis: {
      high: {
        backgroundColor: '$accent9',
        borderRadius: 999,
        color: 'white',
        pressStyle: {},
      },
      medium: {},
      low: {
        backgroundColor: 'none',
        color: '$accent10',
      },
    },
  } as const,
});

export type CButtonProps = React.ComponentProps<typeof CButton>;
