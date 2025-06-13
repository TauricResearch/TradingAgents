import React, { createContext, useContext, useReducer, useEffect } from 'react';
import { message } from 'antd';
import api from '../services/api';

// Auth Action Types
const AUTH_ACTIONS = {
  LOGIN_START: 'LOGIN_START',
  LOGIN_SUCCESS: 'LOGIN_SUCCESS',
  LOGIN_FAILURE: 'LOGIN_FAILURE',
  LOGOUT: 'LOGOUT',
  REGISTER_START: 'REGISTER_START',
  REGISTER_SUCCESS: 'REGISTER_SUCCESS',
  REGISTER_FAILURE: 'REGISTER_FAILURE',
  UPDATE_USER: 'UPDATE_USER',
  SET_LOADING: 'SET_LOADING',
};

// Initial State
const initialState = {
  user: null,
  isAuthenticated: false,
  loading: true,
  error: null,
};

// Auth Reducer
const authReducer = (state, action) => {
  switch (action.type) {
    case AUTH_ACTIONS.LOGIN_START:
    case AUTH_ACTIONS.REGISTER_START:
      return {
        ...state,
        loading: true,
        error: null,
      };
    
    case AUTH_ACTIONS.LOGIN_SUCCESS:
    case AUTH_ACTIONS.REGISTER_SUCCESS:
      return {
        ...state,
        user: action.payload.user,
        isAuthenticated: true,
        loading: false,
        error: null,
      };
    
    case AUTH_ACTIONS.LOGIN_FAILURE:
    case AUTH_ACTIONS.REGISTER_FAILURE:
      return {
        ...state,
        user: null,
        isAuthenticated: false,
        loading: false,
        error: action.payload,
      };
    
    case AUTH_ACTIONS.LOGOUT:
      return {
        ...state,
        user: null,
        isAuthenticated: false,
        loading: false,
        error: null,
      };
    
    case AUTH_ACTIONS.UPDATE_USER:
      return {
        ...state,
        user: { ...state.user, ...action.payload },
      };
    
    case AUTH_ACTIONS.SET_LOADING:
      return {
        ...state,
        loading: action.payload,
      };
    
    default:
      return state;
  }
};

// Create Context
const AuthContext = createContext();

// Auth Provider Component
export const AuthProvider = ({ children }) => {
  const [state, dispatch] = useReducer(authReducer, initialState);

  // 로컬 스토리지에서 토큰 확인 및 사용자 정보 로드
  useEffect(() => {
    const initAuth = async () => {
      const token = localStorage.getItem('access_token');
      
      if (token) {
        try {
          // API에 토큰 설정
          api.defaults.headers.common['Authorization'] = `Bearer ${token}`;
          
          // 사용자 정보 가져오기
          const response = await api.get('/api/auth/user/');
          
          dispatch({
            type: AUTH_ACTIONS.LOGIN_SUCCESS,
            payload: { user: response.data },
          });
        } catch (error) {
          // 토큰이 유효하지 않으면 제거
          localStorage.removeItem('access_token');
          localStorage.removeItem('refresh_token');
          delete api.defaults.headers.common['Authorization'];
          
          dispatch({ type: AUTH_ACTIONS.LOGOUT });
        }
      } else {
        dispatch({ type: AUTH_ACTIONS.SET_LOADING, payload: false });
      }
    };

    initAuth();
  }, []);

  // 로그인 함수
  const login = async (email, password) => {
    dispatch({ type: AUTH_ACTIONS.LOGIN_START });
    
    try {
      const response = await api.post('/api/auth/login/', {
        email,
        password,
      });
      
      const { user, tokens } = response.data;
      
      // 토큰 저장
      localStorage.setItem('access_token', tokens.access);
      localStorage.setItem('refresh_token', tokens.refresh);
      
      // API 헤더에 토큰 설정
      api.defaults.headers.common['Authorization'] = `Bearer ${tokens.access}`;
      
      dispatch({
        type: AUTH_ACTIONS.LOGIN_SUCCESS,
        payload: { user },
      });
      
      message.success('로그인이 완료되었습니다.');
      return { success: true };
      
    } catch (error) {
      const errorMessage = error.response?.data?.message || 
                          error.response?.data?.detail || 
                          '로그인 중 오류가 발생했습니다.';
      
      dispatch({
        type: AUTH_ACTIONS.LOGIN_FAILURE,
        payload: errorMessage,
      });
      
      message.error(errorMessage);
      return { success: false, error: errorMessage };
    }
  };

  // 회원가입 함수
  const register = async (userData) => {
    dispatch({ type: AUTH_ACTIONS.REGISTER_START });
    
    try {
      const response = await api.post('/api/auth/register/', userData);
      
      const { user, tokens } = response.data;
      
      // 토큰 저장
      localStorage.setItem('access_token', tokens.access);
      localStorage.setItem('refresh_token', tokens.refresh);
      
      // API 헤더에 토큰 설정
      api.defaults.headers.common['Authorization'] = `Bearer ${tokens.access}`;
      
      dispatch({
        type: AUTH_ACTIONS.REGISTER_SUCCESS,
        payload: { user },
      });
      
      message.success('회원가입이 완료되었습니다.');
      return { success: true };
      
    } catch (error) {
      const errorMessage = error.response?.data?.message || 
                          '회원가입 중 오류가 발생했습니다.';
      
      dispatch({
        type: AUTH_ACTIONS.REGISTER_FAILURE,
        payload: errorMessage,
      });
      
      message.error(errorMessage);
      return { success: false, error: error.response?.data };
    }
  };

  // 로그아웃 함수
  const logout = () => {
    // 토큰 제거
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    
    // API 헤더에서 토큰 제거
    delete api.defaults.headers.common['Authorization'];
    
    dispatch({ type: AUTH_ACTIONS.LOGOUT });
    
    message.success('로그아웃되었습니다.');
  };

  // 사용자 정보 업데이트
  const updateUser = (userData) => {
    dispatch({
      type: AUTH_ACTIONS.UPDATE_USER,
      payload: userData,
    });
  };

  // 프로필 업데이트
  const updateProfile = async (profileData) => {
    try {
      const response = await api.put('/api/auth/profile/', profileData);
      
      // 사용자 정보 새로고침
      const userResponse = await api.get('/api/auth/user/');
      updateUser(userResponse.data);
      
      message.success('프로필이 업데이트되었습니다.');
      return { success: true, data: response.data };
      
    } catch (error) {
      const errorMessage = error.response?.data?.message || 
                          '프로필 업데이트 중 오류가 발생했습니다.';
      message.error(errorMessage);
      return { success: false, error: error.response?.data };
    }
  };

  // OpenAI API 키 검증
  const checkApiKey = async () => {
    try {
      const response = await api.post('/api/auth/check-api-key/');
      return response.data;
    } catch (error) {
      return { valid: false, message: error.response?.data?.message || '검증 실패' };
    }
  };

  // Context Value
  const value = {
    ...state,
    login,
    register,
    logout,
    updateUser,
    updateProfile,
    checkApiKey,
  };

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
};

// Custom Hook
export const useAuth = () => {
  const context = useContext(AuthContext);
  
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  
  return context;
}; 