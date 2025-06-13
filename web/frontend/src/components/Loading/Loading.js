import React from 'react';
import { Spin } from 'antd';
import { LoadingOutlined } from '@ant-design/icons';
import styled from 'styled-components';

const LoadingContainer = styled.div`
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: ${props => props.fullScreen ? '100vh' : '200px'};
  background-color: ${props => props.fullScreen ? props.theme.colors.background : 'transparent'};
`;

const LoadingContent = styled.div`
  text-align: center;
`;

const LoadingText = styled.div`
  margin-top: ${props => props.theme.spacing.md};
  color: ${props => props.theme.colors.textSecondary};
  font-size: ${props => props.theme.typography.fontSize.base};
`;

const CustomIcon = styled(LoadingOutlined)`
  font-size: ${props => props.size || '24px'};
  color: ${props => props.theme.colors.primary};
`;

const Loading = ({ 
  size = 'large', 
  text = '로딩 중...', 
  fullScreen = false,
  spinning = true 
}) => {
  const iconSize = {
    small: '16px',
    default: '20px',
    large: '24px',
    xlarge: '32px'
  };

  return (
    <LoadingContainer fullScreen={fullScreen}>
      <LoadingContent>
        <Spin 
          indicator={<CustomIcon size={iconSize[size]} />}
          size={size}
          spinning={spinning}
        />
        {text && <LoadingText>{text}</LoadingText>}
      </LoadingContent>
    </LoadingContainer>
  );
};

export default Loading; 