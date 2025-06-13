import React from 'react';
import { Card, Tabs, Typography, Divider, Tag } from 'antd';
import { LineChartOutlined, MessageOutlined, ReadOutlined, WalletOutlined, ProjectOutlined, ExperimentOutlined, SolutionOutlined } from '@ant-design/icons';
import styled from 'styled-components';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

const { Title, Paragraph, Text } = Typography;
const { TabPane } = Tabs;

const ReportContainer = styled(Card)`
  margin-top: ${props => props.theme.spacing.lg};
  .ant-card-body {
    padding: ${props => props.theme.spacing.xl};
  }
`;

const MarkdownWrapper = styled.div`
  h1, h2, h3 {
    margin-top: 24px;
    margin-bottom: 16px;
    font-weight: 600;
  }
  h1 { font-size: 2em; }
  h2 { font-size: 1.5em; border-bottom: 1px solid #f0f0f0; padding-bottom: 8px; }
  h3 { font-size: 1.25em; }
  p { line-height: 1.8; }
  ul, ol { padding-left: 24px; }
  li { margin-bottom: 8px; }
  strong { color: ${props => props.theme.colors.primary}; }
`;

const reportSections = {
    "시장 분석가 리포트": { icon: <LineChartOutlined />, key: 'market' },
    "소셜 미디어 분석가 리포트": { icon: <MessageOutlined />, key: 'social' },
    "뉴스 분석가 리포트": { icon: <ReadOutlined />, key: 'news' },
    "재무 분석가 리포트": { icon: <WalletOutlined />, key: 'fundamentals' },
    "투자 결정 토론 요약": { icon: <ProjectOutlined />, key: 'debate' },
    "최종 투자 계획": { icon: <ExperimentOutlined />, key: 'plan' },
    "최종 거래 결정": { icon: <SolutionOutlined />, key: 'decision' },
};

const ReportDisplay = ({ reportContent }) => {
    if (!reportContent) return null;

    const parsedSections = {};
    const sections = reportContent.split('## ').slice(1);

    sections.forEach(section => {
        const lines = section.split('\n');
        const title = lines[0].trim();
        const content = lines.slice(1).join('\n').trim();
        parsedSections[title] = content;
    });

    const mainTitleMatch = reportContent.match(/^# (.*)/);
    const mainTitle = mainTitleMatch ? mainTitleMatch[1] : "최종 분석 보고서";

    return (
        <ReportContainer>
            <Title level={2} style={{ textAlign: 'center' }}>{mainTitle}</Title>
            <Divider />
            <Tabs defaultActiveKey="market">
                {Object.entries(parsedSections).map(([title, content]) => {
                    const sectionInfo = Object.values(reportSections).find(info => title.includes(Object.keys(reportSections).find(key => reportSections[key] === info))) || {};
                    return (
                        <TabPane
                            tab={<span>{sectionInfo.icon} {title}</span>}
                            key={sectionInfo.key || title}
                        >
                            <MarkdownWrapper>
                                <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
                            </MarkdownWrapper>
                        </TabPane>
                    );
                })}
            </Tabs>
        </ReportContainer>
    );
};

export default ReportDisplay; 