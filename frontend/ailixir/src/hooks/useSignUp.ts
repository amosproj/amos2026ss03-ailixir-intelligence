import { useMutation } from '@tanstack/react-query';
import apiClient from '@/lib/axios';

export interface UserData {
  email: string;
  first_name: string;
  last_name: string;
}

export type SignUpInput = UserData & {
  password: string;
};

export type SignUpResponse = UserData & {
  uid: string;
};

export interface SignUpValidationErrorDetail {
  loc: (string | number)[];
  msg: string;
  type: string;
  input: string;
  ctx?: Record<string, unknown>;
}

export interface SignUpValidationErrorResponse {
  detail: SignUpValidationErrorDetail[];
}

const signUp = async (payload: SignUpInput): Promise<SignUpResponse> => {
  const response = await apiClient.post('/auth/signup', payload);
  return response.data;
};

export function useSignUp() {
  return useMutation({
    mutationFn: signUp,
  });
}
