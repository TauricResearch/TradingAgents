// web/frontend/src/pages/Analysis/Analysis.js

import React, { useState, useEffect } from 'react';
import { Card, Divider, Spin, Alert, Typography, Row, Col } from 'antd';
import styled from 'styled-components';
import api from '../../services/api';
import { useWebSocket } from '../../contexts/WebSocketContext';
import AnalysisForm from './components/AnalysisForm';
import AnalysisDisplay from './components/AnalysisDisplay';

const { Title, Paragraph } = Typography;

const AnalysisContainer = styled.div`
  max-width: 100%;
  margin: 0 auto;
  padding: ${props => props.theme.spacing.lg};
`;

const CustomPageHeader = styled(Card)`
  border: none;
  background-color: transparent;
  .ant-card-body {
    padding: 0;
  }
`;

const Analysis = () => {
  const [currentSessionId, setCurrentSessionId] = useState(null);
  const [analysisStatus, setAnalysisStatus] = useState('idle'); // idle, running, completed, failed
  const [error, setError] = useState(null);
  const [finalReport, setFinalReport] = useState(null);

  const { subscribeToAnalysis, analysisProgress, messages, clearMessages, clearAnalysisProgress } = useWebSocket();

  // WebSocket 메시지로부터 상태 업데이트
  useEffect(() => {
    if (currentSessionId && analysisProgress[currentSessionId]) {
      const progress = analysisProgress[currentSessionId];
      setAnalysisStatus(progress.status);
      if (progress.status === 'completed') {
        setFinalReport(progress.result);
      } else if (progress.status === 'failed') {
        setError(progress.error || '분석 중 알 수 없는 오류가 발생했습니다.');
      }
    }
  }, [analysisProgress, currentSessionId]);

  // 분석 시작 핸들러
  const handleStartAnalysis = async (values) => {
    setAnalysisStatus('starting');
    setError(null);
    setFinalReport(null);
    clearMessages();
    if(currentSessionId) clearAnalysisProgress(currentSessionId);

    try {
      const response = await api.post('/api/trading/start/', values);
      const { session_id } = response.data;
      
      setCurrentSessionId(session_id);
      subscribeToAnalysis(session_id);
      setAnalysisStatus('running');
      
    } catch (err) {
      const errorMessage = err.response?.data?.error || '분석 시작에 실패했습니다.';
      setError(errorMessage);
      setAnalysisStatus('failed');
    }
  };
  
  // 새 분석 시작 핸들러 (Display 컴포넌트에서 호출)
  const handleNewAnalysis = () => {
    if(currentSessionId) clearAnalysisProgress(currentSessionId);
    setCurrentSessionId(null);
    setAnalysisStatus('idle');
    setError(null);
    setFinalReport(null);
    clearMessages();
  };

  const renderContent = () => {
    if (analysisStatus === 'starting') {
        return <div style={{ textAlign: 'center', padding: '50px' }}><Spin size="large" tip="분석을 시작하고 있습니다..." /></div>;
    }
    
    if (currentSessionId && (analysisStatus === 'running' || analysisStatus === 'completed' || analysisStatus === 'failed')) {
      return (
        <AnalysisDisplay
          sessionId={currentSessionId}
          status={analysisStatus}
          progress={analysisProgress[currentSessionId]}
          messages={messages.filter(m => m.sessionId === currentSessionId)}
          finalReport={finalReport}
          onNewAnalysis={handleNewAnalysis}
        />
      );
    }
    
    return <AnalysisForm onStartAnalysis={handleStartAnalysis} loading={analysisStatus === 'starting'} />;
  };

  return (
    <AnalysisContainer>
      <CustomPageHeader>
        <Title level={2}>AI 기반 주식 분석</Title>
        <Paragraph type="secondary">
          관심 있는 종목에 대한 심층 분석을 시작하세요.
        </Paragraph>
      </CustomPageHeader>
      <Divider style={{ margin: '16px 0' }} />

      {error && !currentSessionId && ( // Show top-level error only when no session is active
        <Alert
          message="오류"
          description={error}
          type="error"
          showIcon
          closable
          onClose={() => setError(null)}
          style={{ marginBottom: '24px' }}
        />
      )}
      
      {renderContent()}
    </AnalysisContainer>
  );
};

export default Analysis;