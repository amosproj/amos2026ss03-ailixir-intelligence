import { Button, styled } from 'tamagui';

export const CButton = styled(Button, {
  backgroundColor: 'transparent',

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
      high: {},
      medium: {},
      low: {},
    },
  } as const,
});

export type CButtonProps = React.ComponentProps<typeof CButton>;
