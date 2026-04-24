import { styled, Button as Button } from 'tamagui';

export const CButton = styled(Button, {
  variants: {
    theme: {
      green: {
        backgroundColor: 'green',
        color: 'white',
      },
    },
  } as const,
});

export type CButtonProps = React.ComponentProps<typeof CButton>;
