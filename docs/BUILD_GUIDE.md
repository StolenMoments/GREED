# GREED 모바일 앱 빌드 가이드

앱 정보:
- 앱 이름: GREED
- Bundle ID / Package: `com.personal.greed`
- Expo SDK: ~54.0.33
- React Native: 0.81.5 (New Architecture 활성화)
- 플랫폼: Android / iOS / iPadOS

---

## 목차

1. [공통 사전 준비](#1-공통-사전-준비)
2. [환경변수 설정](#2-환경변수-설정)
3. [Android 빌드](#3-android-빌드)
4. [iOS · iPadOS 빌드](#4-ios--ipados-빌드)
5. [EAS Build (클라우드 빌드)](#5-eas-build-클라우드-빌드)
6. [트러블슈팅](#6-트러블슈팅)

---

## 실행 디렉토리 규칙

이 문서의 모든 명령어는 **반드시 `mobile/` 디렉토리 안에서 실행**해야 한다.  
`package.json`과 `app.json`이 `mobile/` 안에 있기 때문에, 프로젝트 루트(`greed/`)에서 실행하면 Expo가 설정 파일을 찾지 못해 오류가 발생한다.

```bash
# 작업 시작 전 항상 먼저 이동
cd c:\work\greed\mobile
```

Gradle 명령어는 한 단계 더 들어간다:

```bash
cd c:\work\greed\mobile\android
.\gradlew assembleDebug
```

루트에서 실행하면 발생하는 오류:

```
Error: Cannot find Expo in this directory - have you run "npm install" yet?
```

---

## 1. 공통 사전 준비

### Node.js / 패키지 설치

```bash
cd c:\work\greed\mobile
npm install
```

### Expo CLI

```bash
npm install -g expo-cli
npm install -g eas-cli   # 클라우드 빌드 시 필요
```

### API 주소 확인

`mobile/api/client.ts` (또는 상수 파일)에서 백엔드 API URL이 실제 서버 주소를 가리키는지 확인한다.  
로컬 개발 시에는 `http://localhost:3000`, 프로덕션 빌드 시에는 서버 도메인/IP로 설정해야 한다.

---

## 2. 환경변수 설정

Expo는 `app.json`의 `extra` 필드나 `.env` 파일을 통해 환경변수를 주입할 수 있다.  
현재 프로젝트는 `expo-secure-store`를 사용해 API Key를 기기에 저장하므로, 빌드 시 별도 환경변수 설정은 불필요하다.

백엔드 URL을 환경에 따라 분리하고 싶은 경우:

```bash
# .env (mobile/ 디렉토리에 생성)
EXPO_PUBLIC_API_URL=https://your-server-ip-or-domain
```

코드에서는 `process.env.EXPO_PUBLIC_API_URL`으로 접근한다 (`EXPO_PUBLIC_` 접두사 필수).

---

## 3. Android 빌드

### 3-1. 개발용 (Expo Go / Dev Client)

```bash
cd mobile
npx expo start --android
```

- Android 에뮬레이터 또는 실제 기기에서 Expo Go 앱으로 즉시 테스트 가능
- 실기기는 USB 디버깅 활성화 후 연결, 또는 동일 Wi-Fi에서 QR 코드 스캔

### 3-2. 로컬 APK 빌드 (사전 준비)

#### 필수 도구

| 도구 | 버전 권장 | 설치 위치 |
|------|-----------|-----------|
| Android Studio | 최신 | [developer.android.com](https://developer.android.com/studio) |
| Android SDK | API 34 이상 | Android Studio SDK Manager |
| Java (JDK) | 17 | Android Studio 번들 또는 별도 설치 |

환경변수 설정 (Windows):

```powershell
$env:ANDROID_HOME = "$env:LOCALAPPDATA\Android\Sdk"
$env:PATH += ";$env:ANDROID_HOME\platform-tools;$env:ANDROID_HOME\tools"
```

#### Prebuild (네이티브 코드 생성)

```bash
cd mobile
npx expo prebuild --platform android --clean
```

- `android/` 디렉토리가 생성된다.
- `--clean`은 기존 네이티브 폴더를 초기화한다.

#### 디버그 APK 빌드

```bash
cd mobile/android
./gradlew assembleDebug
```

출력 경로: `android/app/build/outputs/apk/debug/app-debug.apk`

#### 릴리즈 APK 빌드

**서명 키 생성 (최초 1회):**

```bash
keytool -genkey -v -keystore greed-release.keystore \
  -alias greed -keyalg RSA -keysize 2048 -validity 10000
```

`android/app/` 디렉토리에 `greed-release.keystore` 저장 후 `android/app/build.gradle`에 서명 설정 추가:

```gradle
android {
    signingConfigs {
        release {
            storeFile file('greed-release.keystore')
            storePassword 'YOUR_STORE_PASSWORD'
            keyAlias 'greed'
            keyPassword 'YOUR_KEY_PASSWORD'
        }
    }
    buildTypes {
        release {
            signingConfig signingConfigs.release
        }
    }
}
```

```bash
cd mobile/android
./gradlew assembleRelease
```

출력 경로: `android/app/build/outputs/apk/release/app-release.apk`

#### 실기기에 설치

```bash
adb install android/app/build/outputs/apk/debug/app-debug.apk
```

---

## 4. iOS · iPadOS 빌드

> **macOS 필수.** Xcode는 macOS에서만 동작한다. Windows/Linux에서는 [섹션 5 EAS Build](#5-eas-build-클라우드-빌드)를 사용한다.

### 4-1. 필수 도구

| 도구 | 버전 권장 |
|------|-----------|
| macOS | 14 Sonoma 이상 |
| Xcode | 16 이상 |
| CocoaPods | 1.15 이상 (`sudo gem install cocoapods`) |

### 4-2. 개발용 (시뮬레이터)

```bash
cd mobile
npx expo start --ios
```

- Xcode Simulator가 자동으로 실행된다.
- 시뮬레이터에서 iPad 기기 타입 선택 시 iPadOS 레이아웃 테스트 가능 (`supportsTablet: true` 설정됨)

### 4-3. 로컬 빌드 (실기기 / 배포)

#### Prebuild

```bash
cd mobile
npx expo prebuild --platform ios --clean
```

- `ios/` 디렉토리가 생성된다.

#### CocoaPods 설치

```bash
cd mobile/ios
pod install
```

#### Xcode에서 빌드

```bash
open mobile/ios/greed.xcworkspace
```

Xcode에서:
1. 상단 scheme을 `greed` (또는 앱 이름)로 선택
2. 실기기 연결 또는 시뮬레이터 선택
3. **Product → Run** (`⌘R`) — 개발 빌드
4. **Product → Archive** — 배포용 아카이브 생성

#### Apple Developer 계정 설정

실기기 테스트 및 TestFlight/App Store 배포에는 Apple Developer 계정 필요:

1. Xcode → **Signing & Capabilities** 탭
2. Team을 Apple Developer 계정으로 설정
3. Bundle Identifier: `com.personal.greed` (app.json과 일치)
4. 자동 서명 (`Automatically manage signing`) 권장

#### TestFlight 배포

1. Xcode에서 **Product → Archive**
2. Organizer → **Distribute App** → App Store Connect 선택
3. App Store Connect에서 TestFlight 빌드 활성화

---

## 5. EAS Build (클라우드 빌드)

EAS Build는 Expo 공식 클라우드 빌드 서비스로, **macOS 없이도 iOS 빌드가 가능**하다.

### 5-1. 초기 설정

```bash
eas login                    # Expo 계정 로그인
cd mobile
eas build:configure          # eas.json 생성
```

생성된 `eas.json` 예시:

```json
{
  "cli": {
    "version": ">= 14.0.0"
  },
  "build": {
    "development": {
      "developmentClient": true,
      "distribution": "internal"
    },
    "preview": {
      "distribution": "internal"
    },
    "production": {}
  },
  "submit": {
    "production": {}
  }
}
```

### 5-2. Android 클라우드 빌드

```bash
# 개발/내부 테스트용 APK
eas build --platform android --profile preview

# 릴리즈 AAB (Google Play 제출용)
eas build --platform android --profile production
```

### 5-3. iOS 클라우드 빌드

```bash
# 내부 테스트용 (Ad Hoc)
eas build --platform ios --profile preview

# App Store 제출용
eas build --platform ios --profile production
```

최초 iOS 빌드 시 EAS가 대화형으로 프로비저닝 프로파일과 인증서를 자동 생성한다.  
Apple Developer 계정 자격 증명 입력 필요.

### 5-4. 전체 플랫폼 동시 빌드

```bash
eas build --platform all --profile production
```

### 5-5. 빌드 상태 확인

```bash
eas build:list
```

또는 `https://expo.dev` 대시보드에서 확인 가능.

---

## 6. 트러블슈팅

### Android: `SDK location not found`

```powershell
# Windows - 환경변수 확인
echo $env:ANDROID_HOME
# 설정되지 않은 경우:
$env:ANDROID_HOME = "$env:LOCALAPPDATA\Android\Sdk"
```

또는 `mobile/android/local.properties` 파일 생성:

```
sdk.dir=C:\\Users\\<사용자명>\\AppData\\Local\\Android\\Sdk
```

### iOS: `pod install` 실패

```bash
sudo gem install cocoapods
cd mobile/ios
pod repo update
pod install
```

### New Architecture 관련 오류

`app.json`에 `"newArchEnabled": true`가 설정되어 있다. 일부 서드파티 라이브러리가 New Architecture를 지원하지 않을 경우 오류가 발생할 수 있다. 해당 라이브러리 GitHub에서 호환성을 확인한다.

### Metro 번들러 캐시 초기화

```bash
cd mobile
npx expo start --clear
```

### `expo-secure-store`: 시뮬레이터 주의사항

`expo-secure-store`는 iOS 시뮬레이터에서 정상 동작하지만 Android 에뮬레이터에서 간헐적 이슈가 있을 수 있다. 실기기 테스트 권장.

### 앱 첫 실행 시 `/setup` 화면으로 이동

앱은 최초 실행 시 API Key가 없으면 자동으로 Setup 화면으로 이동한다 (`_layout.tsx` 로직).  
백엔드 서버 URL과 API Key를 Setup 화면에서 입력하면 정상 작동한다.
