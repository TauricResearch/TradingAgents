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

const AnalysisForm = ({ onStartAnalysis, loading }) => {
    const [form] = Form.useForm();

    const handleSubmit = (values) => {
        onStartAnalysis(values);
    };

    return (
        <FormCard>
            <Title level={4} style={{ textAlign: 'center', marginBottom: '24px' }}>새 분석 시작</Title>
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
                                <Option value="gpt-4o-mini">GPT-4o Mini</Option>
                                <Option value="gpt-4o">GPT-4o</Option>
                                <Option value="gpt-4-turbo">GPT-4 Turbo</Option>
                            </Select>
                        </Form.Item>
                    </Col>
                    <Col span={12}>
                        <Form.Item name="deep_thinker" label="Deep Thinker 모델">
                             <Select>
                                <Option value="gpt-4o">GPT-4o</Option>
                                <Option value="gpt-4-turbo">GPT-4 Turbo</Option>
                            </Select>
                        </Form.Item>
                    </Col>
                </Row>

                <Form.Item style={{ marginTop: '24px' }}>
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