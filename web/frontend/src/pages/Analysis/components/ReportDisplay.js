import React, { useState, useEffect } from 'react';
import { Card, Tabs, Typography, Table, Tag, Row, Col, Spin, Alert } from 'antd';
import styled from 'styled-components';

const { Title, Paragraph } = Typography;

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
`;

const ReportDisplay = ({ reportData }) => {
    const [parsedData, setParsedData] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    useEffect(() => {
        if (reportData) {
            setLoading(true);
            setError(null);
            try {
                const data = JSON.parse(reportData);
                if (data && data.reports) {
                    setParsedData(data);
                } else {
                    throw new Error("Invalid report structure received.");
                }
            } catch (e) {
                console.error("Failed to parse report JSON:", e);
                setError({
                    message: "보고서 파싱에 실패했습니다.",
                    originalData: reportData
                });
            } finally {
                setLoading(false);
            }
        }
    }, [reportData]);

    if (loading) {
        return <Spin tip="보고서를 로딩 중입니다..." size="large" style={{ display: 'block', marginTop: '50px' }} />;
    }

    if (error) {
        return (
            <SectionCard>
                <Alert
                    message="보고서 파싱 오류"
                    description={error.message}
                    type="error"
                    showIcon
                />
                <pre style={{ whiteSpace: 'pre-wrap', backgroundColor: '#f0f2f5', padding: '10px', borderRadius: '4px', marginTop: '16px' }}>
                    {error.originalData}
                </pre>
            </SectionCard>
        );
    }
    
    if (!parsedData) {
        return <Spin tip="보고서 데이터를 기다리는 중..." />;
    }

    const { company_info, reports, final_decision } = parsedData;

    const renderMarketReport = (data) => {
        const { price_summary, indicator_analysis, overall_conclusion } = data;
        const indicatorColumns = [
            { title: '지표', dataIndex: 'indicator', key: 'indicator', width: '20%' },
            { title: '값', dataIndex: 'value', key: 'value', width: '15%' },
            { title: '해석', dataIndex: 'interpretation', key: 'interpretation' },
        ];
        return (
            <>
                <SectionCard title="가격 동향">{price_summary}</SectionCard>
                <SectionCard title="기술적 지표 분석">
                    <Table columns={indicatorColumns} dataSource={indicator_analysis} pagination={false} size="small" rowKey="indicator" />
                </SectionCard>
                <SectionCard title="결론">{overall_conclusion}</SectionCard>
            </>
        );
    };

    const renderFundamentalsReport = (data) => {
        const { company_overview, financial_performance, stock_market_info, analyst_forecasts, insider_sentiment, summary } = data;
        const fundamentalsColumns = [
            { title: '메트릭', dataIndex: 'metric', key: 'metric', width: '40%' },
            { title: '값', dataIndex: 'value', key: 'value', width: '60%' },
        ];
        return (
            <>
                <SectionCard title="회사 개요">{company_overview}</SectionCard>
                <SectionCard title="재무 성과"><Table columns={fundamentalsColumns} dataSource={financial_performance} pagination={false} size="small" rowKey="metric" /></SectionCard>
                <SectionCard title="주식 시장 정보"><Table columns={fundamentalsColumns} dataSource={stock_market_info} pagination={false} size="small" rowKey="metric" /></SectionCard>
                <SectionCard title="애널리스트 전망"><Table columns={fundamentalsColumns} dataSource={analyst_forecasts} pagination={false} size="small" rowKey="metric" /></SectionCard>
                <SectionCard title="내부자 정서 및 거래">{insider_sentiment}</SectionCard>
                <SectionCard title="요약">{summary}</SectionCard>
            </>
        );
    };
    
    const renderGenericReport = (data) => (
        <SectionCard>
             <pre style={{ whiteSpace: 'pre-wrap', fontFamily: 'monospace' }}>
                {JSON.stringify(data, null, 2)}
            </pre>
        </SectionCard>
    );

    const reportRenderers = {
        'market': renderMarketReport,
        'fundamentals': renderFundamentalsReport,
        // Add other specific renderers here
    };

    const tabItems = Object.entries(reports)
        .filter(([key, data]) => data && !data.error)
        .map(([key, data]) => {
            const renderer = reportRenderers[key] || renderGenericReport;
            // Capitalize first letter for label
            const label = key.charAt(0).toUpperCase() + key.slice(1).replace('_', ' ');
            return {
                key: key,
                label: `${label} 리포트`,
                children: renderer(data),
            };
        });

    const getTagColor = (proposal) => {
        switch (proposal?.toUpperCase()) {
            case 'BUY': return 'green';
            case 'SELL': return 'red';
            case 'HOLD': return 'blue';
            default: return 'default';
        }
    }

    return (
        <ReportWrapper>
            <Title level={2}>최종 분석 보고서: {company_info.ticker}</Title>
            <Paragraph type="secondary">분석 기준일: {company_info.analysis_date}</Paragraph>
            <Row align="middle" gutter={16} style={{ marginBottom: 24 }}>
                <Col><Title level={4} style={{ margin: 0 }}>최종 거래 제안:</Title></Col>
                <Col><Tag color={getTagColor(final_decision.final_proposal)} style={{ fontSize: '18px', padding: '6px 12px' }}>{final_decision.final_proposal}</Tag></Col>
            </Row>

            <Tabs defaultActiveKey={tabItems[0]?.key} items={tabItems} />
        </ReportWrapper>
    );
};

export default ReportDisplay; 