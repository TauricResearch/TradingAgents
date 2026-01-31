import { Routes, Route } from 'react-router-dom';
import { ThemeProvider } from './contexts/ThemeContext';
import { SettingsProvider } from './contexts/SettingsContext';
import Header from './components/Header';
import Footer from './components/Footer';
import SettingsModal from './components/SettingsModal';
import Dashboard from './pages/Dashboard';
import History from './pages/History';
import StockDetail from './pages/StockDetail';
import About from './pages/About';

function App() {
  return (
    <ThemeProvider>
      <SettingsProvider>
        <div className="min-h-screen flex flex-col bg-gray-50 dark:bg-slate-900 transition-colors">
          <Header />
          <main className="flex-1 max-w-7xl mx-auto w-full px-3 sm:px-4 lg:px-6 py-4">
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/history" element={<History />} />
              <Route path="/stock/:symbol" element={<StockDetail />} />
              <Route path="/about" element={<About />} />
            </Routes>
          </main>
          <Footer />
          <SettingsModal />
        </div>
      </SettingsProvider>
    </ThemeProvider>
  );
}

export default App;
