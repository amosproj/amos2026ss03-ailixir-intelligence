import { CButton, CInput, CText } from '@/components/atoms';
import { FORM_MESSAGES } from '@/constants/form-messages';
import { ChevronRight } from '@tamagui/lucide-icons-2';
import { Controller, SubmitHandler, useForm } from 'react-hook-form';
import { XStack, YStack } from 'tamagui';

type LoginFormValues = {
  email: string;
  password: string;
};

type LoginFormProps = {
  width?: number;
  onForgotPasswordPress?: () => void;
  onSubmit?: SubmitHandler<LoginFormValues>;
};

export function LoginForm({ width = 300, onForgotPasswordPress, onSubmit = (data) => console.log(data) }: LoginFormProps) {
  const {
    control,
    handleSubmit,
    formState: { errors },
  } = useForm<LoginFormValues>({
    defaultValues: {
      email: '',
      password: '',
    },
  });
  const errorMessage = errors.email?.message ?? errors.password?.message ?? '';

  return (
    <YStack gap={10}>
      <XStack gap={10} justify="flex-start" width={width}>
        <CText fontSize={20} fontWeight="bold">
          {FORM_MESSAGES.title}
        </CText>
      </XStack>

      <Controller
        name="email"
        control={control}
        rules={{ required: FORM_MESSAGES.requiredEmail }}
        render={({ field: { onBlur, onChange, value } }) => (
          <CInput placeholder={FORM_MESSAGES.emailPlaceholder} width={width} value={value} onBlur={onBlur} onChangeText={onChange} autoCapitalize="none" keyboardType="email-address" />
        )}
      />

      <Controller
        name="password"
        control={control}
        rules={{
          required: FORM_MESSAGES.requiredPassword,
          validate: (value) => value === 'password' || FORM_MESSAGES.invalidPassword,
        }}
        render={({ field: { onBlur, onChange, value } }) => (
          <CInput placeholder={FORM_MESSAGES.passwordPlaceholder} width={width} value={value} onBlur={onBlur} onChangeText={onChange} secureTextEntry />
        )}
      />

      <XStack gap={10} justify="space-between" width={width}>
        <CText fontSize={14} color="green" fontWeight={600}>
          {errorMessage}
        </CText>
        <CText fontSize={14} color="darkgray" textDecorationLine="underline" onPress={onForgotPasswordPress}>
          {FORM_MESSAGES.forgotLabel}
        </CText>
      </XStack>
      <XStack width={width} justify="flex-end">
        <CButton icon={ChevronRight} onPress={handleSubmit(onSubmit)}>
          {FORM_MESSAGES.submitLabel}
        </CButton>
      </XStack>
    </YStack>
  );
}
