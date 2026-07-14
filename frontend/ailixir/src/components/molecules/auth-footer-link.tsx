import { CText } from '@/components/atoms';
import { XStack } from 'tamagui';

type AuthFooterLinkProps = {
  text: string;
  linkLabel: string;
  onPress: () => void;
};

export function AuthFooterLink({ text, linkLabel, onPress }: AuthFooterLinkProps) {
  return (
    <XStack width="100%" justify="center" items="center">
      <CText variant="body" color="darkgray">
        {text}{' '}
        <CText variant="body" color="$accent5" onPress={onPress}>
          {linkLabel}
        </CText>
      </CText>
    </XStack>
  );
}
