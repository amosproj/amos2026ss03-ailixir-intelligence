import { create } from 'axios';
import { getAuth } from 'firebase/auth';

const apiClient = create({
  baseURL: 'https://ailixir-backend-5mg2ellzaa-ue.a.run.app',
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
