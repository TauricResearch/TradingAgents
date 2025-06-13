import axios from 'axios';
import { message } from 'antd';

// API 베이스 URL
const BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

// Axios 인스턴스 생성
const api = axios.create({
  baseURL: BASE_URL,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// 요청 인터셉터
api.interceptors.request.use(
  (config) => {
    // 토큰이 있으면 헤더에 추가
    const token = localStorage.getItem('access_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    
    console.log(`API 요청: ${config.method?.toUpperCase()} ${config.url}`);
    return config;
  },
  (error) => {
    console.error('API 요청 오류:', error);
    return Promise.reject(error);
  }
);

// 응답 인터셉터
api.interceptors.response.use(
  (response) => {
    console.log(`API 응답: ${response.config.method?.toUpperCase()} ${response.config.url} - ${response.status}`);
    return response;
  },
  async (error) => {
    const originalRequest = error.config;
    
    console.error('API 응답 오류:', error.response?.status, error.response?.data);
    
    // 401 오류 (인증 실패) 처리
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;
      
      const refreshToken = localStorage.getItem('refresh_token');
      
      if (refreshToken) {
        try {
          // 토큰 갱신 시도
          const response = await axios.post(
            `${BASE_URL}/api/auth/token/refresh/`,
            { refresh: refreshToken }
          );
          
          const newToken = response.data.access;
          localStorage.setItem('access_token', newToken);
          
          // 원래 요청에 새 토큰 적용
          originalRequest.headers.Authorization = `Bearer ${newToken}`;
          api.defaults.headers.common['Authorization'] = `Bearer ${newToken}`;
          
          return api(originalRequest);
          
        } catch (refreshError) {
          console.error('토큰 갱신 실패:', refreshError);
          
          // 리프레시 토큰도 만료된 경우 로그아웃 처리
          localStorage.removeItem('access_token');
          localStorage.removeItem('refresh_token');
          delete api.defaults.headers.common['Authorization'];
          
          // 로그인 페이지로 리디렉션
          window.location.href = '/login';
          
          message.error('세션이 만료되었습니다. 다시 로그인해주세요.');
        }
      } else {
        // 리프레시 토큰이 없는 경우 로그아웃 처리
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
        delete api.defaults.headers.common['Authorization'];
        
        window.location.href = '/login';
        message.error('인증이 필요합니다. 로그인해주세요.');
      }
    }
    
    // 다른 오류들 처리
    if (error.response?.status >= 500) {
      message.error('서버 오류가 발생했습니다. 잠시 후 다시 시도해주세요.');
    } else if (error.response?.status === 403) {
      message.error('접근 권한이 없습니다.');
    } else if (error.response?.status === 404) {
      message.error('요청한 리소스를 찾을 수 없습니다.');
    }
    
    return Promise.reject(error);
  }
);

// API 함수들
export const authAPI = {
  // 로그인
  login: (email, password) =>
    api.post('/api/auth/login/', { email, password }),
  
  // 회원가입
  register: (userData) =>
    api.post('/api/auth/register/', userData),
  
  // 사용자 정보 조회
  getUser: () =>
    api.get('/api/auth/user/'),
  
  // 프로필 조회
  getProfile: () =>
    api.get('/api/auth/profile/'),
  
  // 프로필 업데이트
  updateProfile: (profileData) =>
    api.put('/api/auth/profile/', profileData),
  
  // OpenAI API 키 검증
  checkApiKey: () =>
    api.post('/api/auth/check-api-key/'),
  
  // OpenAI API 키 제거
  removeApiKey: () =>
    api.delete('/api/auth/remove-api-key/'),
  
  // 분석 세션 목록
  getAnalysisSessions: () =>
    api.get('/api/auth/sessions/'),
};

export const tradingAPI = {
  // 분석 설정 정보 조회
  getAnalysisConfig: () =>
    api.get('/api/trading/config/'),
  
  // 분석 옵션 조회
  getAnalysisOptions: () =>
    api.get('/api/trading/options/'),
  
  // 분석 시작
  startAnalysis: (analysisData) =>
    api.post('/api/trading/start/', analysisData),
  
  // 분석 상태 조회
  getAnalysisStatus: (sessionId) =>
    api.get(`/api/trading/status/${sessionId}/`),
  
  // 분석 취소
  cancelAnalysis: (sessionId) =>
    api.post(`/api/trading/cancel/${sessionId}/`),
  
  // 분석 기록 조회
  getAnalysisHistory: () =>
    api.get('/api/trading/history/'),
  
  // 분석 보고서 조회
  getAnalysisReport: (sessionId) =>
    api.get(`/api/trading/report/${sessionId}/`),
  
  // 실행 중인 분석 조회
  getRunningAnalyses: () =>
    api.get('/api/trading/running/'),
};

export default api; 