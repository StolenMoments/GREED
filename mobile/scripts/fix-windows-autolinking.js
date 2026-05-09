#!/usr/bin/env node
// Windows에서 cmd /c가 "Active code page: 65001"을 stdout에 출력해
// expo-modules-autolinking의 JSON 파싱이 실패하는 문제를 수정한다.
// cmd /d /c 로 변경하면 AutoRun 레지스트리 실행이 건너뛰어져 오염이 없어진다.
const fs = require('fs');
const path = require('path');

const target = path.join(
  __dirname,
  '../node_modules/expo-modules-autolinking/android/expo-gradle-plugin',
  'expo-autolinking-plugin-shared/src/main/kotlin/expo/modules/plugin/Os.kt'
);

if (!fs.existsSync(target)) {
  console.log('[fix-windows-autolinking] Os.kt not found, skipping.');
  process.exit(0);
}

const original = fs.readFileSync(target, 'utf8');
const patched = original.replace(
  'listOf("cmd", "/c") + args',
  'listOf("cmd", "/d", "/c") + args'
);

if (original === patched) {
  console.log('[fix-windows-autolinking] Already patched or pattern not found, skipping.');
} else {
  fs.writeFileSync(target, patched, 'utf8');
  console.log('[fix-windows-autolinking] Os.kt patched: cmd /c → cmd /d /c');
}
