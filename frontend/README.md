# Trading Agents Frontend

React + TypeScript로 구현된 Trading Agents 프론트엔드입니다.

## 주요 기능

- **사용자 인증**: 회원가입, 로그인, JWT 토큰 관리
- **분석 관리**: 주식 분석 요청, 진행 상황 추적, 결과 조회
- **실시간 업데이트**: WebSocket을 통한 실시간 분석 진행 상황 업데이트
- **반응형 디자인**: 모바일 및 데스크톱 지원

## 기술 스택

- **React 18**: 메인 프론트엔드 프레임워크
- **TypeScript**: 타입 안정성
- **React Router**: 라우팅
- **Styled Components**: CSS-in-JS 스타일링
- **React Hook Form**: 폼 관리
- **Yup**: 폼 유효성 검사
- **React Query**: 서버 상태 관리
- **Axios**: HTTP 클라이언트
- **React Hot Toast**: 토스트 알림

## 프로젝트 구조

```
src/
├── components/           # 재사용 가능한 컴포넌트
│   ├── auth/            # 인증 관련 컴포넌트
│   ├── analysis/        # 분석 관련 컴포넌트
│   └── common/          # 공통 컴포넌트
├── contexts/            # React Context
├── hooks/               # 커스텀 훅
├── pages/               # 페이지 컴포넌트
├── services/            # API 서비스
├── types/               # TypeScript 타입 정의
└── utils/               # 유틸리티 함수
```

## 설치 및 실행

1. 의존성 설치:
```bash
npm install
```

2. 환경 변수 설정:
```bash
cp .env.example .env
```

3. 개발 서버 실행:
```bash
npm start
```

4. 프로덕션 빌드:
```bash
npm run build
```

## 환경 변수

- `REACT_APP_API_URL`: 백엔드 API 서버 URL
- `REACT_APP_WS_URL`: WebSocket 서버 URL

## 주요 컴포넌트

### 인증 관련
- `LoginForm`: 로그인 폼
- `RegisterForm`: 회원가입 폼
- `AuthContext`: 인증 상태 관리

### 분석 관련
- `AnalysisForm`: 새 분석 요청 폼
- `AnalysisList`: 분석 세션 목록
- `AnalysisResult`: 분석 결과 표시

### 공통
- `Layout`: 공통 레이아웃
- `ProtectedRoute`: 인증된 사용자만 접근 가능한 라우트

## API 연동

백엔드와의 통신을 위해 다음 서비스들을 사용합니다:

- `AuthService`: 인증 관련 API
- `AnalysisService`: 분석 관련 API
- WebSocket 연결을 통한 실시간 업데이트