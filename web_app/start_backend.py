#!/usr/bin/env python3
"""
Startup script for TradingAgents Web Application Backend
"""

import os
import sys
import subprocess

def main():
    # Change to backend directory
    backend_dir = os.path.dirname(os.path.abspath(__file__))
    backend_dir = os.path.join(backend_dir, 'backend')
    
    print("🚀 Starting TradingAgents Web Application Backend")
    print(f"📁 Backend directory: {backend_dir}")
    
    # Check if main.py exists
    main_py = os.path.join(backend_dir, 'main.py')
    if not os.path.exists(main_py):
        print(f"❌ main.py not found at {main_py}")
        return False
    
    # Change to backend directory and run
    os.chdir(backend_dir)
    
    print("🔧 Installing dependencies...")
    try:
        subprocess.run([sys.executable, '-m', 'pip', 'install', 'fastapi', 'uvicorn', 'pydantic', 'python-multipart'], 
                      check=True, capture_output=True)
        print("✅ Dependencies installed")
    except subprocess.CalledProcessError as e:
        print(f"⚠️  Warning: Could not install dependencies: {e}")
        print("   Please install manually: pip install fastapi uvicorn pydantic python-multipart")
    
    print("🌐 Starting FastAPI server...")
    print("   Server will be available at: http://localhost:8000")
    print("   API documentation at: http://localhost:8000/docs")
    print("   Press Ctrl+C to stop the server")
    print("-" * 50)
    
    try:
        # Run the server
        subprocess.run([sys.executable, 'main.py'], check=True)
    except KeyboardInterrupt:
        print("\n🛑 Server stopped by user")
    except subprocess.CalledProcessError as e:
        print(f"❌ Server failed to start: {e}")
        return False
    
    return True

if __name__ == "__main__":
    main()
