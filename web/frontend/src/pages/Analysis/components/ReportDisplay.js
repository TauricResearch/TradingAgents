import React from 'react';
import { Card, Typography } from 'antd';
import styled from 'styled-components';

const { Title } = Typography;

const ReportWrapper = styled.div`
  padding: ${props => props.theme.spacing.md};
  background-color: ${props => props.theme.colors.background};
`;

const SectionCard = styled(Card)`
  margin-bottom: ${props => props.theme.spacing.lg};
  border-radius: ${props => props.theme.borderRadius.lg};
  box-shadow: ${props => props.theme.shadows.md};
  & .ant-card-head {
    background-color: ${props => props.theme.colors.backgroundSecondary};
  }
  & .ant-card-body {
    padding-top: 16px;
    padding-bottom: 16px;
  }
`;

const ReportDisplay = ({ reportData }) => {
    if (!reportData) {
        return null; 
    }

    return (
        <ReportWrapper>
            <SectionCard title="최종 분석 보고서 (원본)">
                <pre style={{ 
                    whiteSpace: 'pre-wrap', 
                    fontFamily: 'monospace', 
                    fontSize: '14px',
                    lineHeight: '1.6'
                }}>
                    {reportData}
                </pre>
            </SectionCard>
        </ReportWrapper>
    );
};

export default ReportDisplay; 