import React, { useState } from 'react';
import { Form, Input, Button, Card, Typography, Alert, Divider } from 'antd';
import { UserOutlined, LockOutlined, MailOutlined, LineChartOutlined } from '@ant-design/icons';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../../contexts/AuthContext';
import styled from 'styled-components';

const { Title, Text } = Typography;

const RegisterContainer = styled.div`
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #1890ff 0%, #722ed1 100%);
  padding: ${props => props.theme.spacing.lg};
`;

const RegisterCard = styled(Card)`
  width: 100%;
  max-width: 450px;
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
    margin-bottom: ${props => props.theme.spacing.md};
  }
`;

const RegisterButton = styled(Button)`
  width: 100%;
  height: 44px;
  font-size: ${props => props.theme.typography.fontSize.base};
  font-weight: ${props => props.theme.typography.fontWeight.medium};
`;

const LoginLink = styled.div`
  text-align: center;
  margin-top: ${props => props.theme.spacing.lg};
  color: ${props => props.theme.colors.textSecondary};
`;

const Register = () => {
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [errors, setErrors] = useState({});
  const { register } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (values) => {
    setLoading(true);
    setErrors({});

    try {
      const result = await register({
        email: values.email,
        username: values.username,
        first_name: values.firstName,
        last_name: values.lastName,
        password: values.password,
        password_confirm: values.confirmPassword,
      });
      
      if (result.success) {
        navigate('/dashboard');
      } else {
        if (result.error && typeof result.error === 'object') {
          setErrors(result.error);
        } else {
          setErrors({ general: result.error || '회원가입에 실패했습니다.' });
        }
      }
    } catch (error) {
      setErrors({ general: '회원가입 중 오류가 발생했습니다.' });
    } finally {
      setLoading(false);
    }
  };

  const handleFormChange = () => {
    if (Object.keys(errors).length > 0) {
      setErrors({});
    }
  };

  // 에러 메시지 포맷팅
  const getErrorMessage = (fieldName) => {
    const error = errors[fieldName];
    if (Array.isArray(error)) {
      return error[0];
    }
    return error;
  };

  return (
    <RegisterContainer>
      <RegisterCard>
        <LogoSection>
          <Logo>
            <LogoIcon />
            <LogoText level={2}>TradingAgents</LogoText>
          </Logo>
          <SubTitle>AI 거래 분석 플랫폼에 가입하세요</SubTitle>
        </LogoSection>

        {errors.general && (
          <Alert
            message={errors.general}
            type="error"
            showIcon
            style={{ marginBottom: 24 }}
          />
        )}

        <StyledForm
          form={form}
          name="register"
          onFinish={handleSubmit}
          onValuesChange={handleFormChange}
          layout="vertical"
          size="large"
        >
          <Form.Item
            label="이메일"
            name="email"
            validateStatus={errors.email ? 'error' : ''}
            help={getErrorMessage('email')}
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
              prefix={<MailOutlined />}
              placeholder="이메일을 입력하세요"
              autoComplete="email"
            />
          </Form.Item>

          <Form.Item
            label="사용자명"
            name="username"
            validateStatus={errors.username ? 'error' : ''}
            help={getErrorMessage('username')}
            rules={[
              {
                required: true,
                message: '사용자명을 입력해주세요.',
              },
              {
                min: 3,
                message: '사용자명은 최소 3자 이상이어야 합니다.',
              },
            ]}
          >
            <Input
              prefix={<UserOutlined />}
              placeholder="사용자명을 입력하세요"
              autoComplete="username"
            />
          </Form.Item>

          <div style={{ display: 'flex', gap: '16px' }}>
            <Form.Item
              label="성"
              name="lastName"
              validateStatus={errors.last_name ? 'error' : ''}
              help={getErrorMessage('last_name')}
              style={{ flex: 1 }}
            >
              <Input placeholder="성을 입력하세요" />
            </Form.Item>

            <Form.Item
              label="이름"
              name="firstName"
              validateStatus={errors.first_name ? 'error' : ''}
              help={getErrorMessage('first_name')}
              style={{ flex: 1 }}
            >
              <Input placeholder="이름을 입력하세요" />
            </Form.Item>
          </div>

          <Form.Item
            label="비밀번호"
            name="password"
            validateStatus={errors.password ? 'error' : ''}
            help={getErrorMessage('password')}
            rules={[
              {
                required: true,
                message: '비밀번호를 입력해주세요.',
              },
              {
                min: 8,
                message: '비밀번호는 최소 8자 이상이어야 합니다.',
              },
            ]}
          >
            <Input.Password
              prefix={<LockOutlined />}
              placeholder="비밀번호를 입력하세요"
              autoComplete="new-password"
            />
          </Form.Item>

          <Form.Item
            label="비밀번호 확인"
            name="confirmPassword"
            validateStatus={errors.password_confirm ? 'error' : ''}
            help={getErrorMessage('password_confirm')}
            dependencies={['password']}
            rules={[
              {
                required: true,
                message: '비밀번호 확인을 입력해주세요.',
              },
              ({ getFieldValue }) => ({
                validator(_, value) {
                  if (!value || getFieldValue('password') === value) {
                    return Promise.resolve();
                  }
                  return Promise.reject(new Error('비밀번호가 일치하지 않습니다.'));
                },
              }),
            ]}
          >
            <Input.Password
              prefix={<LockOutlined />}
              placeholder="비밀번호를 다시 입력하세요"
              autoComplete="new-password"
            />
          </Form.Item>

          <Form.Item style={{ marginTop: '24px' }}>
            <RegisterButton
              type="primary"
              htmlType="submit"
              loading={loading}
            >
              회원가입
            </RegisterButton>
          </Form.Item>
        </StyledForm>

        <Divider>또는</Divider>

        <LoginLink>
          이미 계정이 있으신가요?{' '}
          <Link to="/login" style={{ fontWeight: 500 }}>
            로그인
          </Link>
        </LoginLink>
      </RegisterCard>
    </RegisterContainer>
  );
};

export default Register; 