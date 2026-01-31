import { Routes, Route } from 'react-router-dom';
import Header from './components/Header';
import Footer from './components/Footer';
import Dashboard from './pages/Dashboard';
import History from './pages/History';
import Stocks from './pages/Stocks';
import StockDetail from './pages/StockDetail';

function App() {
  return (
    <div className="min-h-screen flex flex-col">
      <Header />
      <main className="flex-1 max-w-7xl mx-auto w-full px-4 sm:px-6 lg:px-8 py-8">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/history" element={<History />} />
          <Route path="/stocks" element={<Stocks />} />
          <Route path="/stock/:symbol" element={<StockDetail />} />
        </Routes>
      </main>
      <Footer />
    </div>
  );
}

export default App;
