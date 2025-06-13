import React, { useState } from 'react';
import { Form, Input, Button, Card, Typography, Alert, Divider } from 'antd';
import { UserOutlined, LockOutlined, LineChartOutlined } from '@ant-design/icons';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../../contexts/AuthContext';
import styled from 'styled-components';

const { Title, Text } = Typography;

const LoginContainer = styled.div`
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #1890ff 0%, #722ed1 100%);
  padding: ${props => props.theme.spacing.lg};
`;

const LoginCard = styled(Card)`
  width: 100%;
  max-width: 400px;
  box-shadow: ${props => props.theme.shadows.xl};
  border: none;
  border-radius: ${props => props.theme.borderRadius.lg};
`;

const LogoSection = styled.div`
  text-align: center;
  margin-bottom: ${props => props.theme.spacing.xl};
`;

const Logo = styled.div`
  display: flex;
  align-items: center;
  justify-content: center;
  gap: ${props => props.theme.spacing.sm};
  margin-bottom: ${props => props.theme.spacing.md};
`;

const LogoIcon = styled(LineChartOutlined)`
  font-size: 32px;
  color: ${props => props.theme.colors.primary};
`;

const LogoText = styled(Title)`
  margin: 0;
  color: ${props => props.theme.colors.primary};
  font-weight: ${props => props.theme.typography.fontWeight.bold};
`;

const SubTitle = styled(Text)`
  color: ${props => props.theme.colors.textSecondary};
  font-size: ${props => props.theme.typography.fontSize.base};
`;

const StyledForm = styled(Form)`
  .ant-form-item {
    margin-bottom: ${props => props.theme.spacing.lg};
  }
`;

const LoginButton = styled(Button)`
  width: 100%;
  height: 44px;
  font-size: ${props => props.theme.typography.fontSize.base};
  font-weight: ${props => props.theme.typography.fontWeight.medium};
`;

const RegisterLink = styled.div`
  text-align: center;
  margin-top: ${props => props.theme.spacing.lg};
  color: ${props => props.theme.colors.textSecondary};
`;

const Login = () => {
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const { login } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (values) => {
    setLoading(true);
    setError('');

    try {
      const result = await login(values.email, values.password);
      
      if (result.success) {
        navigate('/dashboard');
      } else {
        setError(result.error || '로그인에 실패했습니다.');
      }
    } catch (error) {
      setError('로그인 중 오류가 발생했습니다.');
    } finally {
      setLoading(false);
    }
  };

  const handleFormChange = () => {
    if (error) {
      setError('');
    }
  };

  return (
    <LoginContainer>
      <LoginCard>
        <LogoSection>
          <Logo>
            <LogoIcon />
            <LogoText level={2}>TradingAgents</LogoText>
          </Logo>
          <SubTitle>AI 거래 분석 플랫폼에 로그인하세요</SubTitle>
        </LogoSection>

        {error && (
          <Alert
            message={error}
            type="error"
            showIcon
            style={{ marginBottom: 24 }}
          />
        )}

        <StyledForm
          form={form}
          name="login"
          onFinish={handleSubmit}
          onValuesChange={handleFormChange}
          layout="vertical"
          size="large"
        >
          <Form.Item
            label="이메일"
            name="email"
            rules={[
              {
                required: true,
                message: '이메일을 입력해주세요.',
              },
              {
                type: 'email',
                message: '올바른 이메일 형식을 입력해주세요.',
              },
            ]}
          >
            <Input
              prefix={<UserOutlined />}
              placeholder="이메일을 입력하세요"
              autoComplete="email"
            />
          </Form.Item>

          <Form.Item
            label="비밀번호"
            name="password"
            rules={[
              {
                required: true,
                message: '비밀번호를 입력해주세요.',
              },
            ]}
          >
            <Input.Password
              prefix={<LockOutlined />}
              placeholder="비밀번호를 입력하세요"
              autoComplete="current-password"
            />
          </Form.Item>

          <Form.Item>
            <LoginButton
              type="primary"
              htmlType="submit"
              loading={loading}
            >
              로그인
            </LoginButton>
          </Form.Item>
        </StyledForm>

        <Divider>또는</Divider>

        <RegisterLink>
          계정이 없으신가요?{' '}
          <Link to="/register" style={{ fontWeight: 500 }}>
            회원가입
          </Link>
        </RegisterLink>
      </LoginCard>
    </LoginContainer>
  );
};

export default Login; 