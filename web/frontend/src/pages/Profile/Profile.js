import React from 'react';
import { Card, Typography } from 'antd';
import styled from 'styled-components';

const { Title, Text } = Typography;

const ProfileContainer = styled.div`
  max-width: 800px;
  margin: 0 auto;
`;

const PlaceholderCard = styled(Card)`
  text-align: center;
  padding: ${props => props.theme.spacing.xl};
  background: linear-gradient(135deg, #f0f2f5 0%, #e6f7ff 100%);
`;

const Profile = () => {
  return (
    <ProfileContainer>
      <PlaceholderCard>
        <Title level={2}>프로필 설정 페이지</Title>
        <Text type="secondary">
          여기에 사용자 프로필 설정 기능이 들어갑니다.
          <br />
          개인정보 수정, OpenAI API 키 설정, 기본 분석 옵션 설정 등이 포함됩니다.
        </Text>
      </PlaceholderCard>
    </ProfileContainer>
  );
};

export default Profile; 