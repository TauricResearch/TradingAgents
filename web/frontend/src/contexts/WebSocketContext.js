import React, { createContext, useContext, useEffect, useRef, useState } from 'react';
import { message } from 'antd';
import { useAuth } from './AuthContext';

// WebSocket Context
const WebSocketContext = createContext();

export const WebSocketProvider = ({ children }) => {
  const { user, isAuthenticated } = useAuth();
  const [connected, setConnected] = useState(false);
  const [messages, setMessages] = useState([]);
  const [analysisProgress, setAnalysisProgress] = useState({});
  const wsRef = useRef(null);
  const reconnectTimeoutRef = useRef(null);
  const [reconnectAttempts, setReconnectAttempts] = useState(0);
  const maxReconnectAttempts = 5;

  // WebSocket 연결 함수
  const connect = () => {
    if (!isAuthenticated || !user) {
      return;
    }

    const token = localStorage.getItem('access_token');
    if (!token) {
      return;
    }

    try {
      const wsUrl = `ws://localhost:8000/ws/trading-analysis/?token=${token}`;
      wsRef.current = new WebSocket(wsUrl);

      wsRef.current.onopen = () => {
        console.log('WebSocket 연결됨');
        setConnected(true);
        setReconnectAttempts(0);
        
        // 연결 상태 확인용 ping
        sendMessage({ type: 'ping', timestamp: Date.now() });
      };

      wsRef.current.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          handleMessage(data);
        } catch (error) {
          console.error('WebSocket 메시지 파싱 오류:', error);
        }
      };

      wsRef.current.onclose = (event) => {
        console.log('WebSocket 연결 해제:', event.code, event.reason);
        setConnected(false);
        
        // 자동 재연결 시도 (정상적인 종료가 아닌 경우)
        if (event.code !== 1000 && reconnectAttempts < maxReconnectAttempts) {
          const delay = Math.pow(2, reconnectAttempts) * 1000; // 지수 백오프
          
          reconnectTimeoutRef.current = setTimeout(() => {
            setReconnectAttempts(prev => prev + 1);
            connect();
          }, delay);
        }
      };

      wsRef.current.onerror = (error) => {
        console.error('WebSocket 오류:', error);
        setConnected(false);
      };

    } catch (error) {
      console.error('WebSocket 연결 실패:', error);
      setConnected(false);
    }
  };

  // WebSocket 연결 해제 함수
  const disconnect = () => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
    }
    
    if (wsRef.current) {
      wsRef.current.close(1000, 'User disconnect');
      wsRef.current = null;
    }
    
    setConnected(false);
    setReconnectAttempts(0);
  };

  // 메시지 전송 함수
  const sendMessage = (data) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(data));
    } else {
      console.warn('WebSocket이 연결되지 않음');
    }
  };

  // 분석 세션 구독
  const subscribeToAnalysis = (sessionId) => {
    sendMessage({
      type: 'subscribe_analysis',
      session_id: sessionId
    });
  };

  // 메시지 처리 함수
  const handleMessage = (data) => {
    console.log('WebSocket 메시지 수신:', data);
    
    switch (data.type) {
      case 'connection_established':
        console.log('WebSocket 연결 설정됨:', data.message);
        break;
      
      case 'pong':
        // ping에 대한 응답
        break;
      
      case 'analysis_started':
        setAnalysisProgress(prev => ({
          ...prev,
          [data.session_id]: {
            status: 'running',
            message: data.message,
            progress: 0
          }
        }));
        message.info(data.message);
        break;
      
      case 'analysis_progress':
        setAnalysisProgress(prev => ({
          ...prev,
          [data.session_id]: {
            ...prev[data.session_id],
            status: 'running',
            message: data.content,
            agent: data.agent,
            progress: data.progress,
          }
        }));
        
        // 새로운 메시지 추가
        setMessages(prev => [...prev.slice(-50), {
          id: Date.now(),
          timestamp: new Date(),
          type: data.message_type,
          content: data.content,
          agent: data.agent,
          sessionId: data.session_id
        }]);
        break;
      
      case 'analysis_completed':
        setAnalysisProgress(prev => ({
          ...prev,
          [data.session_id]: {
            status: 'completed',
            message: data.message,
            progress: 100,
            result: data.result,
          }
        }));
        message.success(data.message);
        break;
      
      case 'analysis_failed':
        setAnalysisProgress(prev => ({
          ...prev,
          [data.session_id]: {
            status: 'failed',
            message: data.message,
            progress: 0,
            error: data.message
          }
        }));
        message.error(data.message);
        break;
      
      case 'subscription_confirmed':
        console.log(`분석 세션 ${data.session_id} 구독 완료`);
        break;
      
      case 'subscription_failed':
        message.error(data.message);
        break;
      
      case 'error':
        message.error(data.message);
        break;
      
      default:
        console.log('알 수 없는 메시지 타입:', data.type);
    }
  };

  // 분석 진행 상황 초기화
  const clearAnalysisProgress = (sessionId) => {
    setAnalysisProgress(prev => {
      const newProgress = { ...prev };
      delete newProgress[sessionId];
      return newProgress;
    });
  };

  // 메시지 목록 초기화
  const clearMessages = () => {
    setMessages([]);
  };

  // 사용자 인증 상태 변경 시 WebSocket 연결/해제
  useEffect(() => {
    if (isAuthenticated && user) {
      connect();
    } else {
      disconnect();
    }

    return () => {
      disconnect();
    };
  }, [isAuthenticated, user]);

  // 컴포넌트 언마운트 시 정리
  useEffect(() => {
    return () => {
      disconnect();
    };
  }, []);

  // Context 값
  const value = {
    connected,
    messages,
    analysisProgress,
    sendMessage,
    subscribeToAnalysis,
    clearAnalysisProgress,
    clearMessages,
    reconnectAttempts,
    maxReconnectAttempts
  };

  return (
    <WebSocketContext.Provider value={value}>
      {children}
    </WebSocketContext.Provider>
  );
};

// Custom Hook
export const useWebSocket = () => {
  const context = useContext(WebSocketContext);
  
  if (!context) {
    throw new Error('useWebSocket must be used within a WebSocketProvider');
  }
  
  return context;
}; 