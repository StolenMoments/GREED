import axios from 'axios';
import * as SecureStore from 'expo-secure-store';
import { router } from 'expo-router';

export const API_KEY_STORAGE_KEY = 'greed_api_key';

export const apiKeyStorage = {
  get: ()                   => SecureStore.getItemAsync(API_KEY_STORAGE_KEY),
  set: (key: string)        => SecureStore.setItemAsync(API_KEY_STORAGE_KEY, key),
  delete: ()                => SecureStore.deleteItemAsync(API_KEY_STORAGE_KEY),
};

const BASE_URL = process.env.EXPO_PUBLIC_API_URL ?? 'http://localhost:8001';

const client = axios.create({
  baseURL: BASE_URL,
  timeout: 10_000,
});

client.interceptors.request.use(async (config) => {
  const key = await apiKeyStorage.get();
  if (key) config.headers['X-API-Key'] = key;
  return config;
});

client.interceptors.response.use(
  (res) => res,
  (error) => {
    if (error?.response?.status === 401) {
      router.replace('/setup');
    }
    return Promise.reject(error);
  },
);

export default client;
