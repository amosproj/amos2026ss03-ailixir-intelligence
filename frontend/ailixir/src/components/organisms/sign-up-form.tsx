import { CButton, CInput, CText } from '@/components/atoms';
import { ChevronRight, Eye, EyeOff } from '@tamagui/lucide-icons-2';
import { Controller, SubmitHandler, useForm } from 'react-hook-form';
import { useState } from 'react';
import { XStack, YStack } from 'tamagui';

const PASSWORD_MIN_LENGTH = 8;

export type SignUpFormValues = {
  email: string;
  firstName: string;
  lastName: string;
  password: string;
};

type SignUpFormProps = {
  width?: number | string;
  onSubmit?: SubmitHandler<SignUpFormValues>;
  serverError?: string;
};

export function SignUpForm({ width = '100%', onSubmit = (data) => console.log(data), serverError = '' }: SignUpFormProps) {
  const [isPasswordVisible, setIsPasswordVisible] = useState(false);
  const {
    control,
    handleSubmit,
    formState: { errors },
  } = useForm<SignUpFormValues>({
    defaultValues: {
      email: '',
      firstName: '',
      lastName: '',
      password: '',
    },
  });

  const fieldErrorMessage = errors.email?.message ?? errors.firstName?.message ?? errors.lastName?.message ?? errors.password?.message ?? '';
  // Only show server errors when there are no field errors.
  const errorMessage = fieldErrorMessage || serverError;

  return (
    <YStack gap={12}>
      <YStack gap={6}>
        <CText variant="caption">E-Mail</CText>
        <Controller
          name="email"
          control={control}
          rules={{
            required: 'Email is required',
            validate: (value) => value.includes('@') || 'Invalid email address',
          }}
          render={({ field: { onBlur, onChange, value } }) => (
            <CInput
              placeholder="john.doe@example.com"
              theme="bright"
              width={width}
              value={value}
              onBlur={onBlur}
              onChangeText={onChange}
              autoCapitalize="none"
              autoCorrect={false}
              keyboardType="email-address"
              // iOS Keychain hint — pairs with `textContentType="newPassword"`
              // on the password field below so the system offers to save the
              // credentials after a successful signup.
              textContentType="emailAddress"
              autoComplete="email"
            />
          )}
        />
        {errors.email?.message ? (
          <CText variant="caption" color="$red10">
            {errors.email.message}
          </CText>
        ) : null}
      </YStack>

      <YStack gap={6}>
        <CText variant="caption">First Name</CText>
        <Controller
          name="firstName"
          control={control}
          rules={{ required: 'First name is required' }}
          render={({ field: { onBlur, onChange, value } }) => <CInput placeholder="John" theme="bright" width={width} value={value} onBlur={onBlur} onChangeText={onChange} autoCapitalize="words" />}
        />
        {errors.firstName?.message ? (
          <CText variant="caption" color="$red10">
            {errors.firstName.message}
          </CText>
        ) : null}
      </YStack>

      <YStack gap={6}>
        <CText variant="caption">Last Name</CText>
        <Controller
          name="lastName"
          control={control}
          rules={{ required: 'Last name is required' }}
          render={({ field: { onBlur, onChange, value } }) => <CInput placeholder="Doe" theme="bright" width={width} value={value} onBlur={onBlur} onChangeText={onChange} autoCapitalize="words" />}
        />
        {errors.lastName?.message ? (
          <CText variant="caption" color="$red10">
            {errors.lastName.message}
          </CText>
        ) : null}
      </YStack>

      <YStack gap={6}>
        <CText variant="caption">Password</CText>
        <Controller
          name="password"
          control={control}
          rules={{
            required: 'Password is required',
            minLength: {
              value: PASSWORD_MIN_LENGTH,
              message: `Password required at least ${PASSWORD_MIN_LENGTH} characters`,
            },
          }}
          render={({ field: { onBlur, onChange, value } }) => (
            <XStack gap={0} alignItems="center" paddingRight={8} paddingLeft={0} borderRadius={6} backgroundColor="$gray2" width={width}>
              <CInput
                placeholder="password"
                theme="bright"
                flex={1}
                value={value}
                onBlur={onBlur}
                onChangeText={onChange}
                secureTextEntry={!isPasswordVisible}
                borderWidth={0}
                backgroundColor="transparent"
                // iOS hint: `newPassword` makes the system suggest a strong
                // password and offer to save it to the Keychain on submit.
                textContentType="newPassword"
                autoComplete="new-password"
                autoCapitalize="none"
                autoCorrect={false}
              />
              <CButton size="$3" chromeless onPress={() => setIsPasswordVisible(!isPasswordVisible)} icon={isPasswordVisible ? EyeOff : Eye} />
            </XStack>
          )}
        />
        {errors.password?.message ? (
          <CText variant="caption" color="$red10">
            {errors.password.message}
          </CText>
        ) : null}
      </YStack>

      {errorMessage ? (
        <CText variant="caption" color="$red10">
          {errorMessage}
        </CText>
      ) : null}

      <XStack width={width} justify="flex-end">
        <CButton emphasis="high" iconButton icon={ChevronRight} onPress={handleSubmit(onSubmit)}>
          continue
        </CButton>
      </XStack>
    </YStack>
  );
}
