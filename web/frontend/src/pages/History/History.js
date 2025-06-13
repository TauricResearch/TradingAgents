import React from 'react';
import { Card, Typography } from 'antd';
import styled from 'styled-components';

const { Title, Text } = Typography;

const HistoryContainer = styled.div`
  max-width: 1200px;
  margin: 0 auto;
`;

const PlaceholderCard = styled(Card)`
  text-align: center;
  padding: ${props => props.theme.spacing.xl};
  background: linear-gradient(135deg, #f0f2f5 0%, #e6f7ff 100%);
`;

const History = () => {
  return (
    <HistoryContainer>
      <PlaceholderCard>
        <Title level={2}>분석 기록 페이지</Title>
        <Text type="secondary">
          여기에 사용자의 모든 분석 기록이 표시됩니다.
          <br />
          테이블 형태로 분석 결과를 확인하고 필터링할 수 있습니다.
        </Text>
      </PlaceholderCard>
    </HistoryContainer>
  );
};

export default History; 