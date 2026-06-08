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
  width?: number | string;
  onForgotPasswordPress?: () => void;
  onSubmit?: SubmitHandler<LoginFormValues>;
  serverError?: string;
};

export function LoginForm({ width = '100%', onForgotPasswordPress, onSubmit = (data) => console.log(data), serverError = '' }: LoginFormProps) {
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
  const fieldErrorMessage = errors.email?.message ?? errors.password?.message ?? '';
  // Only show server errors when there are no field errors.
  const errorMessage = fieldErrorMessage || serverError;

  return (
    <YStack gap={10}>
      <YStack gap={6}>
        <CText variant="caption">E-Mail</CText>
        <Controller
          name="email"
          control={control}
          rules={{ required: FORM_MESSAGES.requiredEmail }}
          render={({ field: { onBlur, onChange, value } }) => (
            <CInput
              theme="bright"
              placeholder={FORM_MESSAGES.emailPlaceholder}
              width={width}
              value={value}
              onBlur={onBlur}
              onChangeText={onChange}
              autoCapitalize="none"
              keyboardType="email-address"
            />
          )}
        />
      </YStack>

      <YStack gap={6}>
        <CText variant="caption">Password</CText>
        <Controller
          name="password"
          control={control}
          rules={{
            required: FORM_MESSAGES.requiredPassword,
            // Client-side password validation removed — the only authority on
            // whether a password is correct is Firebase Auth itself. A real
            // wrong-password error surfaces via the catch block in login.tsx
            // (rendered red, below the form). Any hard-coded validator here
            // hides genuine sign-in attempts before they ever hit Firebase.
          }}
          render={({ field: { onBlur, onChange, value } }) => (
            <CInput theme="bright" placeholder={FORM_MESSAGES.passwordPlaceholder} width={width} value={value} onBlur={onBlur} onChangeText={onChange} secureTextEntry />
          )}
        />
      </YStack>

      <XStack gap={10} justify="space-between" width={width}>
        <CText variant="caption" color="green" fontWeight={600}>
          {errorMessage}
        </CText>
        <CText variant="caption" color="darkgray" textDecorationLine="underline" onPress={onForgotPasswordPress}>
          {FORM_MESSAGES.forgotLabel}
        </CText>
      </XStack>
      <XStack width={width} justify="flex-end">
        <CButton iconButton emphasis="high" icon={ChevronRight} onPress={handleSubmit(onSubmit)}>
          {FORM_MESSAGES.submitLabel}
        </CButton>
      </XStack>
    </YStack>
  );
}
