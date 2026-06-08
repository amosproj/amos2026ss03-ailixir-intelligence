import { styled, Input } from 'tamagui';

export const CInput = styled(Input, {
  borderWidth: 0,
  borderColor: 'transparent',
  variants: {
    theme: {
      bright: {
        backgroundColor: '$lightgray',
        color: '$darkgray',
      },
    },
  } as const,
});

export type CInputProps = React.ComponentProps<typeof CInput>;
