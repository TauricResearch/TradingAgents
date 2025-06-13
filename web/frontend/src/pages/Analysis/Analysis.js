import React from 'react';
import { Card, Typography } from 'antd';
import styled from 'styled-components';

const { Title, Text } = Typography;

const AnalysisContainer = styled.div`
  max-width: 800px;
  margin: 0 auto;
`;

const PlaceholderCard = styled(Card)`
  text-align: center;
  padding: ${props => props.theme.spacing.xl};
  background: linear-gradient(135deg, #f0f2f5 0%, #e6f7ff 100%);
`;

const Analysis = () => {
  return (
    <AnalysisContainer>
      <PlaceholderCard>
        <Title level={2}>분석 시작 페이지</Title>
        <Text type="secondary">
          여기에 거래 분석을 시작할 수 있는 폼이 들어갑니다.
          <br />
          종목 선택, 분석 옵션 설정, 분석가 선택 등의 기능이 포함됩니다.
        </Text>
      </PlaceholderCard>
    </AnalysisContainer>
  );
};

export default Analysis; 