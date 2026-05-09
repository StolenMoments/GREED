import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from 'react';
import { useColorScheme } from 'react-native';
import * as SecureStore from 'expo-secure-store';
import { palette } from '@/constants/theme';

type ThemeMode = 'dark' | 'light' | 'system';

type ColorSet = typeof palette.dark | typeof palette.light;

interface ThemeCtx {
  mode: ThemeMode;
  isDark: boolean;
  colors: ColorSet;
  setMode: (mode: ThemeMode) => Promise<void>;
}

const ThemeContext = createContext<ThemeCtx | null>(null);
const THEME_KEY = 'greed_theme_mode';

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const system = useColorScheme();
  const [mode, setModeState] = useState<ThemeMode>('system');

  useEffect(() => {
    SecureStore.getItemAsync(THEME_KEY).then((stored) => {
      if (stored === 'dark' || stored === 'light' || stored === 'system') {
        setModeState(stored);
      }
    });
  }, []);

  const setMode = useCallback(async (next: ThemeMode) => {
    setModeState(next);
    await SecureStore.setItemAsync(THEME_KEY, next);
  }, []);

  const isDark =
    mode === 'dark' || (mode === 'system' && system === 'dark');

  return (
    <ThemeContext.Provider
      value={{ mode, isDark, colors: isDark ? palette.dark : palette.light, setMode }}
    >
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error('useTheme must be inside ThemeProvider');
  return ctx;
}
