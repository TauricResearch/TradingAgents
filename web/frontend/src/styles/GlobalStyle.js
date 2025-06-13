import { createGlobalStyle } from 'styled-components';

const GlobalStyle = createGlobalStyle`
  /* Reset and Base Styles */
  * {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
  }

  html {
    font-size: 16px;
    line-height: 1.5;
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
  }

  body {
    font-family: ${props => props.theme.typography.fontFamily};
    color: ${props => props.theme.colors.text};
    background-color: ${props => props.theme.colors.background};
    font-size: ${props => props.theme.typography.fontSize.base};
    line-height: ${props => props.theme.typography.lineHeight.normal};
  }

  /* Link Styles */
  a {
    color: ${props => props.theme.colors.primary};
    text-decoration: none;
    transition: color ${props => props.theme.transitions.fast};

    &:hover {
      color: ${props => props.theme.colors.primaryHover};
    }

    &:active {
      color: ${props => props.theme.colors.primaryActive};
    }
  }

  /* Button Reset */
  button {
    border: none;
    background: none;
    cursor: pointer;
    font-family: inherit;
  }

  /* Input Reset */
  input, textarea, select {
    font-family: inherit;
    font-size: inherit;
    line-height: inherit;
  }

  /* Remove outline on focus for non-keyboard users */
  :focus:not(:focus-visible) {
    outline: none;
  }

  /* Scrollbar Styles */
  ::-webkit-scrollbar {
    width: 8px;
    height: 8px;
  }

  ::-webkit-scrollbar-track {
    background: ${props => props.theme.colors.backgroundTertiary};
    border-radius: ${props => props.theme.borderRadius.sm};
  }

  ::-webkit-scrollbar-thumb {
    background: ${props => props.theme.colors.border};
    border-radius: ${props => props.theme.borderRadius.sm};
    
    &:hover {
      background: ${props => props.theme.colors.textSecondary};
    }
  }

  /* Ant Design Customizations */
  .ant-layout {
    min-height: 100vh;
  }

  .ant-layout-header {
    background: ${props => props.theme.colors.background};
    border-bottom: 1px solid ${props => props.theme.colors.borderLight};
    padding: 0 ${props => props.theme.spacing.lg};
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  .ant-layout-sider {
    background: ${props => props.theme.colors.background};
    border-right: 1px solid ${props => props.theme.colors.borderLight};
  }

  .ant-layout-content {
    background: ${props => props.theme.colors.backgroundSecondary};
    padding: ${props => props.theme.spacing.lg};
    min-height: calc(100vh - 64px);
  }

  .ant-menu {
    background: transparent;
    border-right: none;
  }

  .ant-menu-item {
    margin: 0;
    border-radius: ${props => props.theme.borderRadius.base};
    margin-bottom: ${props => props.theme.spacing.xs};
    
    &:hover {
      background-color: ${props => props.theme.colors.primaryLight};
    }
  }

  .ant-menu-item-selected {
    background-color: ${props => props.theme.colors.primaryLight} !important;
    
    &::after {
      display: none;
    }
  }

  .ant-card {
    border-radius: ${props => props.theme.borderRadius.md};
    box-shadow: ${props => props.theme.shadows.sm};
    border: 1px solid ${props => props.theme.colors.borderLight};
  }

  .ant-card-head {
    border-bottom: 1px solid ${props => props.theme.colors.borderLight};
  }

  .ant-btn {
    border-radius: ${props => props.theme.borderRadius.base};
    font-weight: ${props => props.theme.typography.fontWeight.medium};
    transition: all ${props => props.theme.transitions.fast};
  }

  .ant-btn-primary {
    background-color: ${props => props.theme.colors.primary};
    border-color: ${props => props.theme.colors.primary};
    
    &:hover, &:focus {
      background-color: ${props => props.theme.colors.primaryHover};
      border-color: ${props => props.theme.colors.primaryHover};
    }
    
    &:active {
      background-color: ${props => props.theme.colors.primaryActive};
      border-color: ${props => props.theme.colors.primaryActive};
    }
  }

  .ant-input, .ant-input-password, .ant-select-selector {
    border-radius: ${props => props.theme.borderRadius.base};
    transition: all ${props => props.theme.transitions.fast};
    
    &:hover {
      border-color: ${props => props.theme.colors.primaryHover};
    }
    
    &:focus, &.ant-input-focused, &.ant-select-focused .ant-select-selector {
      border-color: ${props => props.theme.colors.primary};
      box-shadow: 0 0 0 2px ${props => props.theme.colors.primaryLight};
    }
  }

  .ant-form-item-label > label {
    font-weight: ${props => props.theme.typography.fontWeight.medium};
    color: ${props => props.theme.colors.text};
  }

  .ant-table {
    border-radius: ${props => props.theme.borderRadius.md};
  }

  .ant-table-thead > tr > th {
    background-color: ${props => props.theme.colors.backgroundTertiary};
    border-bottom: 1px solid ${props => props.theme.colors.borderLight};
    font-weight: ${props => props.theme.typography.fontWeight.semibold};
  }

  .ant-table-tbody > tr:hover > td {
    background-color: ${props => props.theme.colors.backgroundSecondary};
  }

  .ant-progress-line {
    .ant-progress-bg {
      transition: all ${props => props.theme.transitions.base};
    }
  }

  .ant-tag {
    border-radius: ${props => props.theme.borderRadius.base};
    font-weight: ${props => props.theme.typography.fontWeight.medium};
  }

  .ant-notification {
    .ant-notification-notice {
      border-radius: ${props => props.theme.borderRadius.md};
      box-shadow: ${props => props.theme.shadows.lg};
    }
  }

  .ant-message {
    .ant-message-notice-content {
      border-radius: ${props => props.theme.borderRadius.md};
      box-shadow: ${props => props.theme.shadows.md};
    }
  }

  /* Custom Status Colors */
  .status-pending {
    color: ${props => props.theme.colors.pending};
  }

  .status-running {
    color: ${props => props.theme.colors.running};
  }

  .status-completed {
    color: ${props => props.theme.colors.completed};
  }

  .status-failed {
    color: ${props => props.theme.colors.failed};
  }

  .status-cancelled {
    color: ${props => props.theme.colors.cancelled};
  }

  /* Trading Colors */
  .bullish {
    color: ${props => props.theme.colors.bullish};
  }

  .bearish {
    color: ${props => props.theme.colors.bearish};
  }

  .neutral {
    color: ${props => props.theme.colors.neutral};
  }

  /* Utility Classes */
  .text-center {
    text-align: center;
  }

  .text-right {
    text-align: right;
  }

  .text-left {
    text-align: left;
  }

  .mb-0 { margin-bottom: 0 !important; }
  .mb-1 { margin-bottom: ${props => props.theme.spacing.xs} !important; }
  .mb-2 { margin-bottom: ${props => props.theme.spacing.sm} !important; }
  .mb-3 { margin-bottom: ${props => props.theme.spacing.md} !important; }
  .mb-4 { margin-bottom: ${props => props.theme.spacing.lg} !important; }
  .mb-5 { margin-bottom: ${props => props.theme.spacing.xl} !important; }

  .mt-0 { margin-top: 0 !important; }
  .mt-1 { margin-top: ${props => props.theme.spacing.xs} !important; }
  .mt-2 { margin-top: ${props => props.theme.spacing.sm} !important; }
  .mt-3 { margin-top: ${props => props.theme.spacing.md} !important; }
  .mt-4 { margin-top: ${props => props.theme.spacing.lg} !important; }
  .mt-5 { margin-top: ${props => props.theme.spacing.xl} !important; }

  .ml-0 { margin-left: 0 !important; }
  .ml-1 { margin-left: ${props => props.theme.spacing.xs} !important; }
  .ml-2 { margin-left: ${props => props.theme.spacing.sm} !important; }
  .ml-3 { margin-left: ${props => props.theme.spacing.md} !important; }
  .ml-4 { margin-left: ${props => props.theme.spacing.lg} !important; }

  .mr-0 { margin-right: 0 !important; }
  .mr-1 { margin-right: ${props => props.theme.spacing.xs} !important; }
  .mr-2 { margin-right: ${props => props.theme.spacing.sm} !important; }
  .mr-3 { margin-right: ${props => props.theme.spacing.md} !important; }
  .mr-4 { margin-right: ${props => props.theme.spacing.lg} !important; }

  .p-0 { padding: 0 !important; }
  .p-1 { padding: ${props => props.theme.spacing.xs} !important; }
  .p-2 { padding: ${props => props.theme.spacing.sm} !important; }
  .p-3 { padding: ${props => props.theme.spacing.md} !important; }
  .p-4 { padding: ${props => props.theme.spacing.lg} !important; }

  /* Loading Animation */
  @keyframes spin {
    0% { transform: rotate(0deg); }
    100% { transform: rotate(360deg); }
  }

  .animate-spin {
    animation: spin 1s linear infinite;
  }

  /* Fade Animations */
  @keyframes fadeIn {
    from { opacity: 0; }
    to { opacity: 1; }
  }

  @keyframes fadeOut {
    from { opacity: 1; }
    to { opacity: 0; }
  }

  .animate-fade-in {
    animation: fadeIn ${props => props.theme.transitions.base};
  }

  .animate-fade-out {
    animation: fadeOut ${props => props.theme.transitions.base};
  }

  /* Responsive Utilities */
  @media (max-width: ${props => props.theme.breakpoints.sm}) {
    .ant-layout-content {
      padding: ${props => props.theme.spacing.md};
    }
    
    .ant-card {
      margin-bottom: ${props => props.theme.spacing.md};
    }
  }
`;

export default GlobalStyle; 