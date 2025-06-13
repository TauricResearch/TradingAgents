// web/frontend/src/pages/Analysis/components/AnalysisForm.js

import React from 'react';
import { Form, Input, Button, Card, Select, Slider, Checkbox, Row, Col, Typography } from 'antd';
import { FundOutlined, SendOutlined } from '@ant-design/icons';
import styled from 'styled-components';

const { Title } = Typography;
const { Option } = Select;

const FormCard = styled(Card)`
  border-radius: ${props => props.theme.borderRadius.lg};
  box-shadow: ${props => props.theme.shadows.lg};
`;

const analystsOptions = [
    { label: '시장 분석가 (Market)', value: 'market' },
    { label: '소셜 분석가 (Social)', value: 'social' },
    { label: '뉴스 분석가 (News)', value: 'news' },
    { label: '재무 분석가 (Fundamentals)', value: 'fundamentals' },
];

const shallowThinkerOptions = [
    { value: 'gpt-4o-mini', label: 'GPT-4o-mini - 빠르고 효율적인 모델' },
    { value: 'gpt-4.1-nano', label: 'GPT-4.1-nano - 초경량 모델' },
    { value: 'gpt-4.1-mini', label: 'GPT-4.1-mini - 준수한 성능의 컴팩트 모델' },
    { value: 'gpt-4o', label: 'GPT-4o - 표준 모델' },
];

const deepThinkerOptions = [
    { value: 'gpt-4.1-nano', label: 'GPT-4.1-nano - 초경량 모델' },
    { value: 'gpt-4.1-mini', label: 'GPT-4.1-mini - 준수한 성능의 컴팩트 모델' },
    { value: 'gpt-4o', label: 'GPT-4o - 표준 모델' },
    { value: 'o4-mini', label: 'o4-mini - 특화된 소형 추론 모델' },
    { value: 'o3-mini', label: 'o3-mini - 경량 고급 추론 모델' },
    { value: 'o3', label: 'o3 - 전체 고급 추론 모델' },
    { value: 'o1', label: 'o1 - 최상위 추론 및 문제 해결 모델' },
];


const AnalysisForm = ({ onStartAnalysis, loading }) => {
    const [form] = Form.useForm();

    const handleSubmit = (values) => {
        onStartAnalysis(values);
    };

    return (
        <FormCard>
            <Title level={4} style={{ textAlign: 'center', marginBottom: '16px' }}>새 분석 시작</Title>
            <Form
                form={form}
                layout="vertical"
                onFinish={handleSubmit}
                initialValues={{
                    research_depth: 3,
                    analysts_selected: ['market', 'news'],
                    shallow_thinker: 'gpt-4o-mini',
                    deep_thinker: 'gpt-4o'
                }}
            >
                <Form.Item
                    name="ticker"
                    label="분석할 주식 Ticker"
                    rules={[{ required: true, message: 'Ticker를 입력해주세요 (예: AAPL, TSLA)' }]}
                >
                    <Input
                        prefix={<FundOutlined />}
                        placeholder="예: AAPL, GOOGL, MSFT"
                        size="large"
                    />
                </Form.Item>

                <Form.Item
                    name="analysts_selected"
                    label="분석가 팀 선택"
                    rules={[{ required: true, message: '최소 한 명의 분석가를 선택해주세요.' }]}
                >
                    <Checkbox.Group style={{ width: '100%' }}>
                        <Row>
                            {analystsOptions.map(option => (
                                <Col span={12} key={option.value}>
                                    <Checkbox value={option.value}>{option.label}</Checkbox>
                                </Col>
                            ))}
                        </Row>
                    </Checkbox.Group>
                </Form.Item>

                <Form.Item
                    name="research_depth"
                    label="분석 깊이"
                >
                    <Slider
                        min={1}
                        max={5}
                        step={2}
                        marks={{ 1: '가볍게', 3: '보통', 5: '심층' }}
                    />
                </Form.Item>

                <Row gutter={16}>
                    <Col span={12}>
                        <Form.Item name="shallow_thinker" label="Shallow Thinker 모델">
                            <Select>
                                {shallowThinkerOptions.map(option => (
                                    <Option key={option.value} value={option.value}>
                                        {option.label}
                                    </Option>
                                ))}
                            </Select>
                        </Form.Item>
                    </Col>
                    <Col span={12}>
                        <Form.Item name="deep_thinker" label="Deep Thinker 모델">
                             <Select>
                                {deepThinkerOptions.map(option => (
                                    <Option key={option.value} value={option.value}>
                                        {option.label}
                                    </Option>
                                ))}
                            </Select>
                        </Form.Item>
                    </Col>
                </Row>

                <Form.Item style={{ marginTop: '16px' }}>
                    <Button
                        type="primary"
                        htmlType="submit"
                        loading={loading}
                        icon={<SendOutlined />}
                        size="large"
                        block
                    >
                        {loading ? '분석 시작 중...' : '분석 시작'}
                    </Button>
                </Form.Item>
            </Form>
        </FormCard>
    );
};

export default AnalysisForm;