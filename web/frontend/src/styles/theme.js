// 테마 설정
const theme = {
  colors: {
    // Primary Colors
    primary: '#1890ff',
    primaryHover: '#40a9ff',
    primaryActive: '#096dd9',
    primaryLight: '#e6f7ff',
    
    // Secondary Colors
    secondary: '#722ed1',
    secondaryHover: '#9254de',
    secondaryActive: '#531dab',
    
    // Success Colors
    success: '#52c41a',
    successHover: '#73d13d',
    successActive: '#389e0d',
    successLight: '#f6ffed',
    
    // Warning Colors
    warning: '#fa8c16',
    warningHover: '#ffa940',
    warningActive: '#d46b08',
    warningLight: '#fff7e6',
    
    // Error Colors
    error: '#ff4d4f',
    errorHover: '#ff7875',
    errorActive: '#d9363e',
    errorLight: '#fff2f0',
    
    // Info Colors
    info: '#1890ff',
    infoHover: '#40a9ff',
    infoActive: '#096dd9',
    infoLight: '#e6f7ff',
    
    // Neutral Colors
    text: '#262626',
    textSecondary: '#8c8c8c',
    textLight: '#bfbfbf',
    textDisabled: '#d9d9d9',
    
    // Background Colors
    background: '#ffffff',
    backgroundSecondary: '#fafafa',
    backgroundTertiary: '#f5f5f5',
    
    // Border Colors
    border: '#d9d9d9',
    borderLight: '#f0f0f0',
    borderSecondary: '#e6f7ff',
    
    // Card & Surface Colors
    cardBg: '#ffffff',
    surfaceBg: '#fafafa',
    
    // Trading Specific Colors
    bullish: '#52c41a',
    bearish: '#ff4d4f',
    neutral: '#fa8c16',
    
    // Analysis Status Colors
    pending: '#faad14',
    running: '#1890ff',
    completed: '#52c41a',
    failed: '#ff4d4f',
    cancelled: '#8c8c8c',
  },
  
  typography: {
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
    
    // Font Sizes
    fontSize: {
      xs: '12px',
      sm: '14px',
      base: '16px',
      lg: '18px',
      xl: '20px',
      '2xl': '24px',
      '3xl': '28px',
      '4xl': '32px',
      '5xl': '36px',
    },
    
    // Font Weights
    fontWeight: {
      light: 300,
      normal: 400,
      medium: 500,
      semibold: 600,
      bold: 700,
    },
    
    // Line Heights
    lineHeight: {
      tight: 1.2,
      normal: 1.5,
      relaxed: 1.75,
    },
  },
  
  spacing: {
    xs: '4px',
    sm: '8px',
    md: '16px',
    lg: '24px',
    xl: '32px',
    '2xl': '48px',
    '3xl': '64px',
    '4xl': '96px',
  },
  
  borderRadius: {
    none: '0',
    sm: '2px',
    base: '6px',
    md: '8px',
    lg: '12px',
    xl: '16px',
    '2xl': '24px',
    full: '50%',
  },
  
  shadows: {
    none: 'none',
    sm: '0 1px 3px 0 rgba(0, 0, 0, 0.1), 0 1px 2px 0 rgba(0, 0, 0, 0.06)',
    base: '0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06)',
    md: '0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05)',
    lg: '0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04)',
    xl: '0 25px 50px -12px rgba(0, 0, 0, 0.25)',
  },
  
  breakpoints: {
    xs: '480px',
    sm: '576px',
    md: '768px',
    lg: '992px',
    xl: '1200px',
    xxl: '1600px',
  },
  
  zIndex: {
    dropdown: 1000,
    sticky: 1020,
    fixed: 1030,
    modalBackdrop: 1040,
    modal: 1050,
    popover: 1060,
    tooltip: 1070,
    notification: 1080,
  },
  
  transitions: {
    fast: '150ms ease-in-out',
    base: '250ms ease-in-out',
    slow: '350ms ease-in-out',
  },
  
  // Component Specific Themes
  components: {
    button: {
      height: {
        sm: '24px',
        base: '32px',
        lg: '40px',
      },
      padding: {
        sm: '4px 15px',
        base: '4px 15px',
        lg: '6px 15px',
      },
    },
    
    input: {
      height: {
        sm: '24px',
        base: '32px',
        lg: '40px',
      },
    },
    
    card: {
      padding: '24px',
      borderRadius: '8px',
      boxShadow: '0 1px 2px 0 rgba(0, 0, 0, 0.03), 0 1px 6px -1px rgba(0, 0, 0, 0.02), 0 2px 4px 0 rgba(0, 0, 0, 0.02)',
    },
    
    layout: {
      header: {
        height: '64px',
        background: '#ffffff',
        borderBottom: '1px solid #f0f0f0',
      },
      sidebar: {
        width: '200px',
        collapsedWidth: '80px',
        background: '#001529',
      },
      content: {
        padding: '24px',
        background: '#fafafa',
        minHeight: 'calc(100vh - 64px)',
      },
    },
  },
};

export default theme; 