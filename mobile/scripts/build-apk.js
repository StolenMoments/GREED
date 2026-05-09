const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');

const projectRoot = path.resolve(__dirname, '..');
const envFile = path.join(projectRoot, '.env.mobile');
const localEnvFile = path.join(projectRoot, '.env.local');
const androidDir = path.join(projectRoot, 'android');

function parseEnv(content) {
  const result = {};

  for (const rawLine of content.split(/\r?\n/)) {
    const line = rawLine.trim();

    if (!line || line.startsWith('#')) {
      continue;
    }

    const equalIndex = line.indexOf('=');
    if (equalIndex === -1) {
      continue;
    }

    const key = line.slice(0, equalIndex).trim();
    let value = line.slice(equalIndex + 1).trim();

    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }

    result[key] = value;
  }

  return result;
}

function run(command, args, options = {}) {
  const result = spawnSync(command, args, {
    cwd: options.cwd || projectRoot,
    env: options.env || process.env,
    stdio: 'inherit',
    shell: process.platform === 'win32',
  });

  if (result.error) {
    console.error(result.error.message);
    process.exit(1);
  }

  if (result.status !== 0) {
    process.exit(result.status || 1);
  }
}

if (!fs.existsSync(envFile)) {
  console.error('Missing mobile/.env.mobile. Create it before building the APK.');
  process.exit(1);
}

if (!fs.existsSync(androidDir)) {
  console.error('Missing mobile/android. Run "npm run prebuild:android" first.');
  process.exit(1);
}

const args = process.argv.slice(2);
const isDebug = args.includes('--debug');
const shouldPrebuild = args.includes('--prebuild');
const gradleArgs = args.includes('--')
  ? args.slice(args.indexOf('--') + 1)
  : [];

const envValues = parseEnv(fs.readFileSync(envFile, 'utf8'));
const buildEnv = {
  ...process.env,
  ...envValues,
  EXPO_NO_DOTENV: '1',
};

const loadedKeys = Object.keys(envValues).sort();
console.log(`Using .env.mobile (${loadedKeys.join(', ') || 'no variables'})`);

if (fs.existsSync(localEnvFile)) {
  console.log('Ignoring .env.local for APK build.');
}

if (shouldPrebuild) {
  run(
    process.platform === 'win32' ? 'npx.cmd' : 'npx',
    ['expo', 'prebuild', '--platform', 'android'],
    { env: buildEnv }
  );
}

const gradlew = process.platform === 'win32' ? 'gradlew.bat' : './gradlew';
const task = isDebug ? 'assembleDebug' : 'assembleRelease';

run(gradlew, [task, ...gradleArgs], {
  cwd: androidDir,
  env: buildEnv,
});
