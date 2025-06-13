import React, { useState, useEffect } from 'react';
import { Card, Row, Col, Statistic, Typography, Button, Table, Tag, Space } from 'antd';
import { 
  LineChartOutlined, 
  TrophyOutlined, 
  ClockCircleOutlined, 
  RocketOutlined,
  PlayCircleOutlined,
  EyeOutlined
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../contexts/AuthContext';
import { useWebSocket } from '../../contexts/WebSocketContext';
import { tradingAPI } from '../../services/api';
import styled from 'styled-components';
import Loading from '../../components/Loading/Loading';

const { Title, Text } = Typography;

const DashboardContainer = styled.div`
  max-width: 1200px;
  margin: 0 auto;
`;

const WelcomeCard = styled(Card)`
  background: linear-gradient(135deg, #1890ff 0%, #722ed1 100%);
  color: white;
  margin-bottom: ${props => props.theme.spacing.lg};
  border: none;
  
  .ant-card-body {
    padding: ${props => props.theme.spacing.xl};
  }
`;

const WelcomeContent = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
  
  @media (max-width: ${props => props.theme.breakpoints.md}) {
    flex-direction: column;
    text-align: center;
    gap: ${props => props.theme.spacing.lg};
  }
`;

const WelcomeText = styled.div`
  h2 {
    color: white !important;
    margin-bottom: ${props => props.theme.spacing.sm};
  }
  
  p {
    color: rgba(255, 255, 255, 0.85);
    font-size: ${props => props.theme.typography.fontSize.lg};
    margin: 0;
  }
`;

const QuickActions = styled.div`
  display: flex;
  gap: ${props => props.theme.spacing.md};
  
  @media (max-width: ${props => props.theme.breakpoints.sm}) {
    flex-direction: column;
    width: 100%;
  }
`;

const StatsCard = styled(Card)`
  height: 100%;
  
  .ant-statistic-title {
    color: ${props => props.theme.colors.textSecondary};
    font-weight: ${props => props.theme.typography.fontWeight.medium};
  }
  
  .ant-statistic-content {
    color: ${props => props.theme.colors.text};
  }
`;

const RecentAnalysisCard = styled(Card)`
  .ant-card-head-title {
    font-weight: ${props => props.theme.typography.fontWeight.semibold};
  }
`;

const Dashboard = () => {
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState({
    totalAnalyses: 0,
    runningAnalyses: 0,
    completedAnalyses: 0,
    thisMonth: 0
  });
  const [recentAnalyses, setRecentAnalyses] = useState([]);
  const { user } = useAuth();
  const { connected, messages } = useWebSocket();
  const navigate = useNavigate();

  useEffect(() => {
    loadDashboardData();
  }, []);

  const loadDashboardData = async () => {
    try {
      setLoading(true);
      
      // 분석 기록 가져오기
      const historyResponse = await tradingAPI.getAnalysisHistory();
      const analyses = historyResponse.data.results || [];
      
      // 실행 중인 분석 가져오기
      const runningResponse = await tradingAPI.getRunningAnalyses();
      const runningAnalyses = runningResponse.data.results || [];
      
      // 통계 계산
      const totalCount = analyses.length;
      const runningCount = runningAnalyses.length;
      const completedCount = analyses.filter(a => a.status === 'completed').length;
      
      // 이번 달 분석 수
      const currentMonth = new Date().getMonth();
      const currentYear = new Date().getFullYear();
      const thisMonthCount = analyses.filter(analysis => {
        const analysisDate = new Date(analysis.created_at);
        return analysisDate.getMonth() === currentMonth && 
               analysisDate.getFullYear() === currentYear;
      }).length;
      
      setStats({
        totalAnalyses: totalCount,
        runningAnalyses: runningCount,
        completedAnalyses: completedCount,
        thisMonth: thisMonthCount
      });
      
      // 최근 분석 5개만 표시
      setRecentAnalyses(analyses.slice(0, 5));
      
    } catch (error) {
      console.error('대시보드 데이터 로드 실패:', error);
    } finally {
      setLoading(false);
    }
  };

  const getStatusColor = (status) => {
    const colors = {
      pending: 'orange',
      running: 'blue',
      completed: 'green',
      failed: 'red',
      cancelled: 'default'
    };
    return colors[status] || 'default';
  };

  const getStatusText = (status) => {
    const texts = {
      pending: '대기 중',
      running: '실행 중',
      completed: '완료',
      failed: '실패',
      cancelled: '취소됨'
    };
    return texts[status] || status;
  };

  const columns = [
    {
      title: '종목',
      dataIndex: 'ticker',
      key: 'ticker',
      render: (ticker) => <strong>{ticker}</strong>
    },
    {
      title: '분석 날짜',
      dataIndex: 'analysis_date',
      key: 'analysis_date',
    },
    {
      title: '상태',
      dataIndex: 'status',
      key: 'status',
      render: (status) => (
        <Tag color={getStatusColor(status)}>
          {getStatusText(status)}
        </Tag>
      )
    },
    {
      title: '생성일',
      dataIndex: 'created_at',
      key: 'created_at',
      render: (date) => new Date(date).toLocaleDateString('ko-KR')
    },
    {
      title: '작업',
      key: 'actions',
      render: (_, record) => (
        <Space>
          <Button 
            type="link" 
            icon={<EyeOutlined />}
            onClick={() => navigate(`/history`)}
          >
            보기
          </Button>
        </Space>
      )
    }
  ];

  if (loading) {
    return <Loading text="대시보드를 로드하는 중..." />;
  }

  return (
    <DashboardContainer>
      {/* 환영 메시지 */}
      <WelcomeCard>
        <WelcomeContent>
          <WelcomeText>
            <Title level={2}>
              안녕하세요, {user?.first_name || user?.username}님! 👋
            </Title>
            <Text>
              AI 기반 거래 분석으로 더 나은 투자 결정을 내려보세요.
            </Text>
          </WelcomeText>
          
          <QuickActions>
            <Button 
              type="primary" 
              size="large"
              icon={<RocketOutlined />}
              onClick={() => navigate('/analysis')}
              style={{ 
                background: 'rgba(255, 255, 255, 0.2)',
                borderColor: 'rgba(255, 255, 255, 0.4)',
                color: 'white'
              }}
            >
              새 분석 시작
            </Button>
            <Button 
              size="large"
              icon={<EyeOutlined />}
              onClick={() => navigate('/history')}
              style={{ 
                background: 'rgba(255, 255, 255, 0.1)',
                borderColor: 'rgba(255, 255, 255, 0.3)',
                color: 'white'
              }}
            >
              분석 기록
            </Button>
          </QuickActions>
        </WelcomeContent>
      </WelcomeCard>

      {/* 통계 카드들 */}
      <Row gutter={[16, 16]} style={{ marginBottom: '24px' }}>
        <Col xs={24} sm={12} lg={6}>
          <StatsCard>
            <Statistic
              title="총 분석 수"
              value={stats.totalAnalyses}
              prefix={<LineChartOutlined />}
            />
          </StatsCard>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <StatsCard>
            <Statistic
              title="실행 중"
              value={stats.runningAnalyses}
              prefix={<PlayCircleOutlined />}
              valueStyle={{ color: '#1890ff' }}
            />
          </StatsCard>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <StatsCard>
            <Statistic
              title="완료된 분석"
              value={stats.completedAnalyses}
              prefix={<TrophyOutlined />}
              valueStyle={{ color: '#52c41a' }}
            />
          </StatsCard>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <StatsCard>
            <Statistic
              title="이번 달"
              value={stats.thisMonth}
              prefix={<ClockCircleOutlined />}
            />
          </StatsCard>
        </Col>
      </Row>

      {/* 최근 분석 */}
      <RecentAnalysisCard 
        title="최근 분석"
        extra={
          <Button type="link" onClick={() => navigate('/history')}>
            모두 보기
          </Button>
        }
      >
        {recentAnalyses.length > 0 ? (
          <Table
            columns={columns}
            dataSource={recentAnalyses}
            pagination={false}
            rowKey="id"
            size="small"
          />
        ) : (
          <div style={{ textAlign: 'center', padding: '40px' }}>
            <Text type="secondary">아직 분석 기록이 없습니다.</Text>
            <br />
            <Button 
              type="primary" 
              style={{ marginTop: '16px' }}
              onClick={() => navigate('/analysis')}
            >
              첫 번째 분석 시작하기
            </Button>
          </div>
        )}
      </RecentAnalysisCard>

      {/* WebSocket 연결 상태 정보 */}
      {!connected && (
        <Card 
          style={{ marginTop: '16px', borderColor: '#ff4d4f' }}
          size="small"
        >
          <Text type="danger">
            실시간 업데이트 연결이 끊어졌습니다. 일부 기능이 제한될 수 있습니다.
          </Text>
        </Card>
      )}
    </DashboardContainer>
  );
};

export default Dashboard; 