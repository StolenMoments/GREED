import React, { useEffect, useState } from 'react';
import { ActivityIndicator, View } from 'react-native';
import { Redirect, Tabs } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '@/contexts/ThemeContext';
import { fontSize } from '@/constants/theme';
import { apiKeyStorage } from '@/api/client';

type IoniconsName = React.ComponentProps<typeof Ionicons>['name'];

function TabIcon({
  name,
  focused,
  color,
}: {
  name: IoniconsName;
  focused: boolean;
  color: string;
}) {
  return <Ionicons name={name} size={22} color={color} />;
}

export default function TabsLayout() {
  const { colors } = useTheme();
  const [hasApiKey, setHasApiKey] = useState<boolean | null>(null);

  useEffect(() => {
    let mounted = true;

    apiKeyStorage.get()
      .then((key) => {
        if (mounted) setHasApiKey(Boolean(key));
      })
      .catch(() => {
        if (mounted) setHasApiKey(false);
      });

    return () => {
      mounted = false;
    };
  }, []);

  if (hasApiKey === null) {
    return (
      <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.bg }}>
        <ActivityIndicator color={colors.accent} />
      </View>
    );
  }

  if (!hasApiKey) return <Redirect href="/setup" />;

  return (
    <Tabs
      screenOptions={{
        headerStyle:      { backgroundColor: colors.bg },
        headerTintColor:  colors.textPri,
        headerTitleStyle: {
          fontFamily: 'Archivo_700Bold',
          fontSize:   fontSize.lg,
        },
        tabBarStyle: {
          backgroundColor: colors.surface1,
          borderTopColor:  colors.border,
          borderTopWidth:  1,
        },
        tabBarActiveTintColor:   colors.accent,
        tabBarInactiveTintColor: colors.textTer,
        tabBarLabelStyle: {
          fontFamily: 'Archivo_600SemiBold',
          fontSize:   fontSize.xs,
          marginBottom: 2,
        },
      }}
    >
      <Tabs.Screen
        name="index"
        options={{
          title: '분석 목록',
          tabBarIcon: ({ focused, color }) => (
            <TabIcon
              name={focused ? 'bar-chart' : 'bar-chart-outline'}
              focused={focused}
              color={color}
            />
          ),
        }}
      />
      <Tabs.Screen
        name="stocks"
        options={{
          title: '종목',
          tabBarIcon: ({ focused, color }) => (
            <TabIcon
              name={focused ? 'layers' : 'layers-outline'}
              focused={focused}
              color={color}
            />
          ),
        }}
      />
    </Tabs>
  );
}
