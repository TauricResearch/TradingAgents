import React, { useRef, useEffect } from 'react';
import { Card, Progress, Timeline, Button, Result, Typography, Empty, Tag } from 'antd';
import { FileDoneOutlined, RedoOutlined } from '@ant-design/icons';
import styled from 'styled-components';
import ReportDisplay from './ReportDisplay';

const { Title, Paragraph, Text } = Typography;

const DisplayCard = styled(Card)`
  border-radius: ${props => props.theme.borderRadius.lg};
  box-shadow: ${props => props.theme.shadows.lg};
  margin-top: ${props => props.theme.spacing.lg};
  border-radius: ${props => props.theme.borderRadius.md};
  background-color: ${props => props.theme.colors.backgroundSecondary};
`;

const TimelineContainer = styled.div`
  max-height: 400px;
  overflow-y: auto;
  padding: ${props => props.theme.spacing.md};
  border: 1px solid ${props => props.theme.colors.border};
  border-radius: ${props => props.theme.borderRadius.md};
  background-color: ${props => props.theme.colors.backgroundSecondary};
`;

const ReportContainer = styled.div`
  margin-top: ${props => props.theme.spacing.lg};
`;

const agentTagColors = {
    market: 'blue',
    social: 'cyan',
    news: 'green',
    fundamentals: 'purple',
};

const AnalysisDisplay = ({ sessionId, status, progress, messages, finalReport, onNewAnalysis }) => {
    const timelineEndRef = useRef(null);

    useEffect(() => {
        timelineEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [messages]);

    const renderRunningState = () => (
        <>
            <Title level={4}>분석 진행 중...</Title>
            <Paragraph type="secondary">AI 분석가들이 정보를 수집하고 분석하고 있습니다. (세션 ID: {sessionId})</Paragraph>
            <Progress percent={progress?.progress || 0} status="active" />
            <Paragraph style={{ textAlign: 'center', marginTop: '10px' }}>{progress?.message}</Paragraph>
            
            <TimelineContainer>
                <Timeline>
                    {messages.length > 0 ? messages.map(msg => (
                        <Timeline.Item key={msg.id}>
                            <Text strong>
                                <Tag color={agentTagColors[msg.agent] || 'default'}>{msg.agent}</Tag>
                                {new Date(msg.timestamp).toLocaleTimeString()}
                            </Text>
                            <Paragraph style={{ marginLeft: '10px' }}>{msg.content}</Paragraph>
                        </Timeline.Item>
                    )) : <Empty description="실시간 분석 로그가 여기에 표시됩니다." />}
                </Timeline>
                <div ref={timelineEndRef} />
            </TimelineContainer>
        </>
    );

    const renderCompletedState = () => (
        <Result
            status="success"
            title="분석이 성공적으로 완료되었습니다!"
            icon={<FileDoneOutlined />}
            subTitle="아래에서 생성된 최종 보고서를 확인하세요."
            extra={[
                <Button type="primary" key="new" icon={<RedoOutlined />} onClick={onNewAnalysis}>
                    새 분석 시작
                </Button>
            ]}
        />
    );

    const renderFailedState = () => (
        <Result
            status="error"
            title="분석에 실패했습니다."
            subTitle={progress?.error || '알 수 없는 오류가 발생했습니다.'}
            extra={[
                <Button type="primary" key="retry" icon={<RedoOutlined />} onClick={onNewAnalysis}>
                    다시 시도
                </Button>
            ]}
        />
    );

    return (
        <DisplayCard>
            {status === 'running' && renderRunningState()}
            {status === 'completed' && renderCompletedState()}
            {status === 'failed' && renderFailedState()}
            
            {status === 'completed' && finalReport && (
                <ReportContainer>
                    <ReportDisplay reportData={finalReport} />
                </ReportContainer>
            )}
        </DisplayCard>
    );
};

export default AnalysisDisplay; 