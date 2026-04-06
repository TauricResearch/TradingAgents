import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { ConfigProvider, theme } from 'antd'
import App from './App'
import './index.css'

// Apple Design System Ant Design configuration
const appleTheme = {
  algorithm: theme.defaultAlgorithm,
  token: {
    colorPrimary: '#0071e3',
    colorSuccess: '#22c55e',
    colorError: '#dc2626',
    colorWarning: '#f59e0b',
    colorInfo: '#0071e3',
    colorBgBase: '#ffffff',
    colorBgContainer: '#ffffff',
    colorBgElevated: '#f5f5f7',
    colorBorder: 'rgba(0, 0, 0, 0.08)',
    colorText: '#1d1d1f',
    colorTextSecondary: 'rgba(0, 0, 0, 0.48)',
    borderRadius: 8,
    fontFamily: '"SF Pro Text", -apple-system, BlinkMacSystemFont, "Helvetica Neue", Helvetica, Arial, sans-serif',
    wireframe: false,
  },
  components: {
    Button: {
      borderRadius: 8,
    },
    Select: {
      borderRadius: 11,
    },
    Table: {
      borderRadius: 8,
    },
  },
}

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter>
      <ConfigProvider theme={appleTheme}>
        <App />
      </ConfigProvider>
    </BrowserRouter>
  </React.StrictMode>
)
