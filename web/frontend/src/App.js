import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { ConfigProvider } from 'antd';
import koKR from 'antd/locale/ko_KR';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import { WebSocketProvider } from './contexts/WebSocketContext';
import { ThemeProvider } from 'styled-components';
import GlobalStyle from './styles/GlobalStyle';
import theme from './styles/theme';

// Components
import Layout from './components/Layout/Layout';
import Login from './pages/Login/Login';
import Register from './pages/Register/Register';
import Dashboard from './pages/Dashboard/Dashboard';
import Analysis from './pages/Analysis/Analysis';
import History from './pages/History/History';
import Profile from './pages/Profile/Profile';
import Loading from './components/Loading/Loading';

// Protected Route Component
const ProtectedRoute = ({ children }) => {
  const { user, loading } = useAuth();
  
  if (loading) {
    return <Loading />;
  }
  
  return user ? children : <Navigate to="/login" />;
};

// Public Route Component (redirect to dashboard if already logged in)
const PublicRoute = ({ children }) => {
  const { user, loading } = useAuth();
  
  if (loading) {
    return <Loading />;
  }
  
  return !user ? children : <Navigate to="/dashboard" />;
};

function App() {
  return (
    <ConfigProvider locale={koKR}>
      <ThemeProvider theme={theme}>
        <GlobalStyle />
        <AuthProvider>
          <Router>
            <Routes>
              {/* Public Routes */}
              <Route 
                path="/login" 
                element={
                  <PublicRoute>
                    <Login />
                  </PublicRoute>
                } 
              />
              <Route 
                path="/register" 
                element={
                  <PublicRoute>
                    <Register />
                  </PublicRoute>
                } 
              />
              
              {/* Protected Routes */}
              <Route 
                path="/*" 
                element={
                  <ProtectedRoute>
                    <WebSocketProvider>
                      <Layout>
                        <Routes>
                          <Route path="/dashboard" element={<Dashboard />} />
                          <Route path="/analysis" element={<Analysis />} />
                          <Route path="/history" element={<History />} />
                          <Route path="/profile" element={<Profile />} />
                          <Route path="/" element={<Navigate to="/dashboard" />} />
                        </Routes>
                      </Layout>
                    </WebSocketProvider>
                  </ProtectedRoute>
                } 
              />
            </Routes>
          </Router>
        </AuthProvider>
      </ThemeProvider>
    </ConfigProvider>
  );
}

export default App; 