import { useState, useEffect, lazy, Suspense } from 'react'
import { Routes, Route, NavLink, useLocation, useNavigate } from 'react-router-dom'
import {
  FundOutlined,
  MonitorOutlined,
  FileTextOutlined,
  ClusterOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
} from '@ant-design/icons'

const ScreeningPanel = lazy(() => import('./pages/ScreeningPanel'))
const AnalysisMonitor = lazy(() => import('./pages/AnalysisMonitor'))
const ReportsViewer = lazy(() => import('./pages/ReportsViewer'))
const BatchManager = lazy(() => import('./pages/BatchManager'))

const navItems = [
  { path: '/', icon: <FundOutlined />, label: '筛选', key: '1' },
  { path: '/monitor', icon: <MonitorOutlined />, label: '监控', key: '2' },
  { path: '/reports', icon: <FileTextOutlined />, label: '报告', key: '3' },
  { path: '/batch', icon: <ClusterOutlined />, label: '批量', key: '4' },
]

function Layout({ children }) {
  const [collapsed, setCollapsed] = useState(false)
  const [isMobile, setIsMobile] = useState(false)
  const location = useLocation()

  useEffect(() => {
    const checkMobile = () => setIsMobile(window.innerWidth < 768)
    checkMobile()
    window.addEventListener('resize', checkMobile)
    return () => window.removeEventListener('resize', checkMobile)
  }, [])

  const currentPage = navItems.find(item =>
    item.path === '/'
      ? location.pathname === '/'
      : location.pathname.startsWith(item.path)
  )?.label || 'TradingAgents'

  return (
    <div className="dashboard-layout">
      {/* Sidebar - Apple Glass Navigation */}
      {!isMobile && (
        <aside className={`sidebar ${collapsed ? 'collapsed' : ''}`}>
          <div className="sidebar-logo">
            {!collapsed && <span>TradingAgents</span>}
            {collapsed && <span style={{ fontSize: 12, letterSpacing: '0.1em' }}>TA</span>}
          </div>

          <nav className="sidebar-nav">
            {navItems.map((item) => (
              <NavLink
                key={item.path}
                to={item.path}
                className={({ isActive }) =>
                  `nav-item ${isActive ? 'active' : ''}`
                }
                end={item.path === '/'}
                aria-label={`${item.label} (按${item.key}切换)`}
              >
                {item.icon}
                {!collapsed && <span>{item.label}</span>}
              </NavLink>
            ))}
          </nav>

          <div style={{ padding: 'var(--space-2)' }}>
            <button
              onClick={() => setCollapsed(!collapsed)}
              aria-label={collapsed ? '展开侧边栏' : '收起侧边栏'}
              className="sidebar-collapse-btn"
            >
              {collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
              {!collapsed && <span>收起</span>}
            </button>
          </div>
        </aside>
      )}

      {/* Main Content */}
      <main className={`main-content ${collapsed && !isMobile ? 'sidebar-collapsed' : ''}`}>
        {!isMobile && (
          <header className="topbar">
            <div className="topbar-title">{currentPage}</div>
            <div className="topbar-date">
              {new Date().toLocaleDateString('zh-CN', {
                year: 'numeric',
                month: 'long',
                day: 'numeric',
              })}
            </div>
          </header>
        )}

        <div className="page-content">
          {children}
        </div>
      </main>

      {/* Mobile TabBar */}
      {isMobile && (
        <nav className="mobile-tabbar" aria-label="移动端导航">
          {navItems.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              className={({ isActive }) =>
                `mobile-tab-item ${isActive ? 'active' : ''}`
              }
              end={item.path === '/'}
              aria-label={item.label}
            >
              <span className="mobile-tab-icon">{item.icon}</span>
              <span className="mobile-tab-label">{item.label}</span>
            </NavLink>
          ))}
        </nav>
      )}
    </div>
  )
}

export default function App() {
  const navigate = useNavigate()

  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return
      // Close modals on Escape
      if (e.key === 'Escape') {
        document.querySelector('.ant-modal-wrap')?.click()
        return
      }
      // Navigation shortcuts
      switch (e.key) {
        case '1': navigate('/'); break
        case '2': navigate('/monitor'); break
        case '3': navigate('/reports'); break
        case '4': navigate('/batch'); break
        default: break
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [navigate])

  return (
    <Layout>
      <Suspense fallback={
        <div style={{ padding: 'var(--space-12)', textAlign: 'center' }}>
          <div className="loading-pulse">加载中...</div>
        </div>
      }>
        <Routes>
          <Route path="/" element={<ScreeningPanel />} />
          <Route path="/monitor" element={<AnalysisMonitor />} />
          <Route path="/reports" element={<ReportsViewer />} />
          <Route path="/batch" element={<BatchManager />} />
        </Routes>
      </Suspense>
    </Layout>
  )
}
