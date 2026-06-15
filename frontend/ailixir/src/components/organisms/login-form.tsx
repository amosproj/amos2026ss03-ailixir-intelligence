import { CButton, CInput, CText } from '@/components/atoms';
import { FORM_MESSAGES } from '@/constants/form-messages';
import { ChevronRight, Eye, EyeOff } from '@tamagui/lucide-icons-2';
import { Controller, SubmitHandler, useForm } from 'react-hook-form';
import { useState } from 'react';
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
  const [isPasswordVisible, setIsPasswordVisible] = useState(false);
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
            <XStack gap={8} alignItems="center" width={width}>
              <CInput theme="bright" placeholder={FORM_MESSAGES.passwordPlaceholder} flex={1} value={value} onBlur={onBlur} onChangeText={onChange} secureTextEntry={!isPasswordVisible} />
              <CButton size="$3" chromeless onPress={() => setIsPasswordVisible(!isPasswordVisible)} icon={isPasswordVisible ? EyeOff : Eye} />
            </XStack>
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
