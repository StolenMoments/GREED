import React, { useEffect, useState } from 'react';
import { View } from 'react-native';
import { Stack, router } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import * as SplashScreen from 'expo-splash-screen';
import {
  useFonts,
  Archivo_400Regular,
  Archivo_600SemiBold,
  Archivo_700Bold,
} from '@expo-google-fonts/archivo';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ThemeProvider, useTheme } from '@/contexts/ThemeContext';
import { apiKeyStorage } from '@/api/client';

SplashScreen.preventAutoHideAsync();

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 60_000,
    },
  },
});

function RootStack() {
  const { colors, isDark } = useTheme();
  const [apiKeyChecked, setApiKeyChecked] = useState(false);

  useEffect(() => {
    apiKeyStorage.get().then((key) => {
      setApiKeyChecked(true);
      if (!key) {
        router.replace('/setup');
      } else {
        router.replace('/(tabs)');
      }
    });
  }, []);

  if (!apiKeyChecked) return null;

  return (
    <>
      <StatusBar style={isDark ? 'light' : 'dark'} />
      <Stack
        screenOptions={{
          headerStyle:      { backgroundColor: colors.bg },
          headerTintColor:  colors.textPri,
          headerTitleStyle: { fontFamily: 'Archivo_700Bold', fontSize: 17 },
          contentStyle:     { backgroundColor: colors.bg },
        }}
      >
        <Stack.Screen name="(tabs)"       options={{ headerShown: false }} />
        <Stack.Screen name="setup"        options={{ headerShown: false }} />
        <Stack.Screen
          name="analysis/[id]"
          options={{
            title:           '',
            headerBackTitle: '목록',
          }}
        />
      </Stack>
    </>
  );
}

export default function Layout() {
  const [fontsLoaded] = useFonts({
    Archivo_400Regular,
    Archivo_600SemiBold,
    Archivo_700Bold,
  });

  useEffect(() => {
    if (fontsLoaded) SplashScreen.hideAsync();
  }, [fontsLoaded]);

  if (!fontsLoaded) return null;

  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <RootStack />
      </ThemeProvider>
    </QueryClientProvider>
  );
}
