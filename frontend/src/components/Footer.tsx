import { TrendingUp, Github, Twitter } from 'lucide-react';

export default function Footer() {
  return (
    <footer className="bg-white border-t border-gray-200 mt-auto">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-8">
          {/* Brand */}
          <div className="col-span-1 md:col-span-2">
            <div className="flex items-center gap-2 mb-4">
              <div className="w-10 h-10 bg-gradient-to-br from-nifty-500 to-nifty-700 rounded-xl flex items-center justify-center">
                <TrendingUp className="w-6 h-6 text-white" />
              </div>
              <h2 className="text-xl font-display font-bold gradient-text">Nifty50 AI</h2>
            </div>
            <p className="text-gray-600 text-sm max-w-md">
              AI-powered stock recommendations for Nifty 50 stocks. Using advanced machine learning
              to analyze market trends, technical indicators, and news sentiment.
            </p>
          </div>

          {/* Quick Links */}
          <div>
            <h3 className="font-semibold text-gray-900 mb-4">Quick Links</h3>
            <ul className="space-y-2">
              <li><a href="/" className="text-gray-600 hover:text-nifty-600 text-sm">Dashboard</a></li>
              <li><a href="/history" className="text-gray-600 hover:text-nifty-600 text-sm">History</a></li>
              <li><a href="/stocks" className="text-gray-600 hover:text-nifty-600 text-sm">All Stocks</a></li>
            </ul>
          </div>

          {/* Legal */}
          <div>
            <h3 className="font-semibold text-gray-900 mb-4">Legal</h3>
            <ul className="space-y-2">
              <li><a href="#" className="text-gray-600 hover:text-nifty-600 text-sm">Disclaimer</a></li>
              <li><a href="#" className="text-gray-600 hover:text-nifty-600 text-sm">Privacy Policy</a></li>
              <li><a href="#" className="text-gray-600 hover:text-nifty-600 text-sm">Terms of Use</a></li>
            </ul>
          </div>
        </div>

        <div className="border-t border-gray-200 mt-8 pt-8 flex flex-col sm:flex-row justify-between items-center gap-4">
          <p className="text-gray-500 text-sm">
            © {new Date().getFullYear()} Nifty50 AI. All rights reserved.
          </p>
          <div className="flex items-center gap-4">
            <a href="#" className="text-gray-400 hover:text-gray-600">
              <Github className="w-5 h-5" />
            </a>
            <a href="#" className="text-gray-400 hover:text-gray-600">
              <Twitter className="w-5 h-5" />
            </a>
          </div>
        </div>

        {/* Disclaimer */}
        <div className="mt-8 p-4 bg-gray-50 rounded-lg">
          <p className="text-xs text-gray-500 text-center">
            <strong>Disclaimer:</strong> This website provides AI-generated stock recommendations for
            educational purposes only. These are not financial advice. Always do your own research
            and consult with a qualified financial advisor before making investment decisions.
            Past performance does not guarantee future results.
          </p>
        </div>
      </div>
    </footer>
  );
}
