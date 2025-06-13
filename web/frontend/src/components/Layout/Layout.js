import React, { useState } from 'react';
import { Layout as AntLayout, Menu, Avatar, Dropdown, Button, Badge, Typography } from 'antd';
import { 
  DashboardOutlined, 
  LineChartOutlined, 
  HistoryOutlined, 
  UserOutlined, 
  LogoutOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  BellOutlined,
  WifiOutlined,
  DisconnectOutlined
} from '@ant-design/icons';
import { useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../../contexts/AuthContext';
import { useWebSocket } from '../../contexts/WebSocketContext';
import styled from 'styled-components';

const { Header, Sider, Content } = AntLayout;
const { Title } = Typography;

const StyledLayout = styled(AntLayout)`
  min-height: 100vh;
`;

const StyledHeader = styled(Header)`
  background: ${props => props.theme.colors.background};
  border-bottom: 1px solid ${props => props.theme.colors.borderLight};
  padding: 0 ${props => props.theme.spacing.lg};
  display: flex;
  align-items: center;
  justify-content: space-between;
  position: sticky;
  top: 0;
  z-index: ${props => props.theme.zIndex.sticky};
`;

const StyledSider = styled(Sider)`
  background: ${props => props.theme.colors.background};
  border-right: 1px solid ${props => props.theme.colors.borderLight};
  
  .ant-layout-sider-trigger {
    background: ${props => props.theme.colors.backgroundSecondary};
    border-top: 1px solid ${props => props.theme.colors.borderLight};
    color: ${props => props.theme.colors.text};
  }
`;

const StyledContent = styled(Content)`
  background: ${props => props.theme.colors.backgroundSecondary};
  padding: ${props => props.theme.spacing.lg};
  overflow-y: auto;
`;

const HeaderLeft = styled.div`
  display: flex;
  align-items: center;
  gap: ${props => props.theme.spacing.md};
`;

const HeaderRight = styled.div`
  display: flex;
  align-items: center;
  gap: ${props => props.theme.spacing.md};
`;

const Logo = styled.div`
  display: flex;
  align-items: center;
  gap: ${props => props.theme.spacing.sm};
  font-weight: ${props => props.theme.typography.fontWeight.bold};
  font-size: ${props => props.theme.typography.fontSize.lg};
  color: ${props => props.theme.colors.primary};
`;

const ConnectionStatus = styled.div`
  display: flex;
  align-items: center;
  gap: ${props => props.theme.spacing.xs};
  font-size: ${props => props.theme.typography.fontSize.sm};
  color: ${props => props.connected ? props.theme.colors.success : props.theme.colors.error};
`;

const UserInfo = styled.div`
  display: flex;
  align-items: center;
  gap: ${props => props.theme.spacing.sm};
`;

const MainLayout = ({ children }) => {
  const [collapsed, setCollapsed] = useState(false);
  const { user, logout } = useAuth();
  const { connected, reconnectAttempts, maxReconnectAttempts } = useWebSocket();
  const location = useLocation();
  const navigate = useNavigate();

  // 메뉴 아이템 정의
  const menuItems = [
    {
      key: '/dashboard',
      icon: <DashboardOutlined />,
      label: '대시보드',
    },
    {
      key: '/analysis',
      icon: <LineChartOutlined />,
      label: '분석 시작',
    },
    {
      key: '/history',
      icon: <HistoryOutlined />,
      label: '분석 기록',
    },
    {
      key: '/profile',
      icon: <UserOutlined />,
      label: '프로필',
    },
  ];

  // 사용자 드롭다운 메뉴
  const userMenuItems = [
    {
      key: 'profile',
      icon: <UserOutlined />,
      label: '프로필',
      onClick: () => navigate('/profile'),
    },
    {
      type: 'divider',
    },
    {
      key: 'logout',
      icon: <LogoutOutlined />,
      label: '로그아웃',
      onClick: logout,
    },
  ];

  const handleMenuClick = ({ key }) => {
    navigate(key);
  };

  const toggleCollapsed = () => {
    setCollapsed(!collapsed);
  };

  return (
    <StyledLayout>
      <StyledSider 
        trigger={null} 
        collapsible 
        collapsed={collapsed}
        width={240}
        collapsedWidth={80}
      >
        <div style={{ padding: '16px', borderBottom: `1px solid #f0f0f0` }}>
          {!collapsed ? (
            <Logo>
              <LineChartOutlined style={{ fontSize: '24px' }} />
              TradingAgents
            </Logo>
          ) : (
            <div style={{ textAlign: 'center' }}>
              <LineChartOutlined style={{ fontSize: '24px', color: '#1890ff' }} />
            </div>
          )}
        </div>
        
        <Menu
          theme="light"
          mode="inline"
          selectedKeys={[location.pathname]}
          items={menuItems}
          onClick={handleMenuClick}
          style={{ border: 'none', paddingTop: '16px' }}
        />
      </StyledSider>

      <AntLayout>
        <StyledHeader>
          <HeaderLeft>
            <Button
              type="text"
              icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
              onClick={toggleCollapsed}
              style={{
                fontSize: '16px',
                width: 40,
                height: 40,
              }}
            />
            
            <Title level={4} style={{ margin: 0, color: '#262626' }}>
              {menuItems.find(item => item.key === location.pathname)?.label || 'TradingAgents'}
            </Title>
          </HeaderLeft>

          <HeaderRight>
            {/* WebSocket 연결 상태 */}
            <ConnectionStatus connected={connected}>
              {connected ? (
                <>
                  <WifiOutlined />
                  <span>연결됨</span>
                </>
              ) : (
                <>
                  <DisconnectOutlined />
                  <span>
                    {reconnectAttempts > 0 
                      ? `재연결 중... (${reconnectAttempts}/${maxReconnectAttempts})`
                      : '연결 끊김'
                    }
                  </span>
                </>
              )}
            </ConnectionStatus>

            {/* 알림 아이콘 */}
            <Badge count={0} showZero={false}>
              <Button
                type="text"
                icon={<BellOutlined />}
                style={{ fontSize: '16px' }}
              />
            </Badge>

            {/* 사용자 정보 */}
            <Dropdown
              menu={{ items: userMenuItems }}
              placement="bottomRight"
              arrow
            >
              <UserInfo>
                <Avatar 
                  icon={<UserOutlined />} 
                  style={{ 
                    backgroundColor: '#1890ff',
                    cursor: 'pointer'
                  }}
                />
                {!collapsed && (
                  <span style={{ cursor: 'pointer' }}>
                    {user?.username || user?.email}
                  </span>
                )}
              </UserInfo>
            </Dropdown>
          </HeaderRight>
        </StyledHeader>

        <StyledContent>
          {children}
        </StyledContent>
      </AntLayout>
    </StyledLayout>
  );
};

export default MainLayout; 