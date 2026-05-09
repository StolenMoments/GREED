import React, { useState } from 'react';
import {
  KeyboardAvoidingView,
  Platform,
  Pressable,
  SafeAreaView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { router } from 'expo-router';
import { useTheme } from '@/contexts/ThemeContext';
import { apiKeyStorage } from '@/api/client';
import { spacing, fontSize, radius } from '@/constants/theme';

export default function SetupScreen() {
  const { colors, isDark } = useTheme();
  const [key, setKey] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  async function save() {
    const trimmed = key.trim();
    if (!trimmed) {
      setError('API 키를 입력해주세요.');
      return;
    }
    setSaving(true);
    await apiKeyStorage.set(trimmed);
    router.replace('/(tabs)');
  }

  return (
    <SafeAreaView style={[styles.safe, { backgroundColor: colors.bg }]}>
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        style={styles.flex}
      >
        <View style={styles.container}>
          <View style={styles.brand}>
            <Text style={[styles.logo, { color: colors.accent }]}>GREED</Text>
            <Text style={[styles.sub, { color: colors.textSec }]}>
              주식 기술적 분석 뷰어
            </Text>
          </View>

          <View style={styles.form}>
            <Text style={[styles.label, { color: colors.textSec }]}>
              API 키
            </Text>
            <TextInput
              style={[
                styles.input,
                {
                  backgroundColor: colors.surface1,
                  borderColor:     error ? '#D94535' : colors.border,
                  color:           colors.textPri,
                },
              ]}
              placeholder="백엔드에서 발급한 API 키를 입력하세요"
              placeholderTextColor={colors.textTer}
              value={key}
              onChangeText={(v) => { setKey(v); setError(''); }}
              autoCapitalize="none"
              autoCorrect={false}
              returnKeyType="done"
              onSubmitEditing={save}
            />
            {!!error && (
              <Text style={styles.errorText}>{error}</Text>
            )}

            <Pressable
              onPress={save}
              disabled={saving}
              style={({ pressed }) => [
                styles.btn,
                { backgroundColor: colors.accent },
                pressed && styles.pressed,
                saving && { opacity: 0.6 },
              ]}
            >
              <Text style={styles.btnText}>
                {saving ? '저장 중…' : '저장'}
              </Text>
            </Pressable>
          </View>

          <Text style={[styles.hint, { color: colors.textTer }]}>
            backend-mobile 서버의 MOBILE_API_KEY 값을 사용하세요.
          </Text>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1 },
  flex: { flex: 1 },
  container: {
    flex:           1,
    justifyContent: 'center',
    paddingHorizontal: spacing.xl,
    gap:            spacing.xl,
  },
  brand: {
    alignItems: 'center',
    gap:        spacing.xs,
  },
  logo: {
    fontSize:      40,
    fontFamily:    'Archivo_700Bold',
    letterSpacing: 8,
  },
  sub: {
    fontSize:   fontSize.sm,
    letterSpacing: 1,
  },
  form: {
    gap: spacing.md,
  },
  label: {
    fontSize:   fontSize.sm,
    fontWeight: '600',
    letterSpacing: 0.5,
  },
  input: {
    borderWidth:   1,
    borderRadius:  radius.md,
    paddingHorizontal: spacing.base,
    paddingVertical:   spacing.md,
    fontSize:      fontSize.base,
    fontFamily:    'Archivo_400Regular',
  },
  errorText: {
    fontSize: fontSize.xs,
    color:    '#D94535',
    marginTop: -spacing.xs,
  },
  btn: {
    borderRadius:    radius.md,
    paddingVertical: spacing.md,
    alignItems:      'center',
    marginTop:       spacing.sm,
  },
  btnText: {
    fontSize:   fontSize.base,
    fontWeight: '700',
    fontFamily: 'Archivo_700Bold',
    color:      '#1A1000',
  },
  pressed: {
    opacity: 0.8,
  },
  hint: {
    fontSize:   fontSize.xs,
    textAlign:  'center',
    lineHeight: fontSize.xs * 1.6,
  },
});
