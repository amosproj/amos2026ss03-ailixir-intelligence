import { styled, Input } from 'tamagui';

export const CInput = styled(Input, {
  variants: {
    theme: {
      green: {
        backgroundColor: 'green',
        color: 'white',
      },
    },
  } as const,
});

export type CInputProps = React.ComponentProps<typeof CInput>;
