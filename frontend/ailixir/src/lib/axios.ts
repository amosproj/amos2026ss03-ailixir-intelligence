import { create } from 'axios';
import { getAuth } from 'firebase/auth';
import { API_BASE_URL } from '@/lib/api-config';

const apiClient = create({
  baseURL: API_BASE_URL,
});

apiClient.interceptors.request.use(async (config) => {
  const auth = getAuth();
  const user = auth.currentUser;
  if (user) {
    const token = await user.getIdToken();
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

export default apiClient;
