import { CText } from '@/components/atoms';
import { XStack } from 'tamagui';

type ListFilterProps = {
  items: string[];
  active?: string;
  setActive?: (value: string) => void;
};

export function ListFilters({ items, active, setActive }: ListFilterProps) {
  return (
    <XStack mt={5} justify="flex-start" gap={15} items="center" px={4}>
      {items.map((item) => (
        <CText key={item} variant="lead" color={active === item ? '#E25353' : undefined} onPress={setActive ? () => setActive(item) : undefined}>
          {item}
        </CText>
      ))}
    </XStack>
  );
}
