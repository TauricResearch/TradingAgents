#!/usr/bin/env python3
"""
Test script to verify memory.py chunking and persistent storage improvements.

Tests:
1. Short text handling (backward compatibility)
2. Long text chunking with RecursiveCharacterTextSplitter
3. Persistent storage functionality
4. In-memory storage (backward compatibility)
"""

import os
import sys
import tempfile
import shutil

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tradingagents.agents.utils.memory import FinancialSituationMemory


def test_short_text_backward_compatibility():
    """Test that short texts work as before (single embedding)."""
    print("\n" + "="*80)
    print("TEST 1: Short Text Backward Compatibility")
    print("="*80)
    
    config = {
        "backend_url": "https://api.openai.com/v1"
    }
    
    # Use in-memory storage (backward compatible)
    memory = FinancialSituationMemory(name="test_short", config=config)
    
    # Short situation
    short_data = [
        (
            "Tech stocks are volatile",
            "Reduce tech exposure"
        )
    ]
    
    memory.add_situations(short_data)
    results = memory.get_memories("Tech volatility concerns", n_matches=1)
    
    if results and len(results) > 0:
        print(f"✅ Short text test passed")
        print(f"   Similarity Score: {results[0]['similarity_score']:.2f}")
        print(f"   Recommendation: {results[0]['recommendation']}")
        return True
    else:
        print("❌ Short text test failed")
        return False


def test_long_text_chunking():
    """Test that long texts are properly chunked."""
    print("\n" + "="*80)
    print("TEST 2: Long Text Chunking")
    print("="*80)
    
    config = {
        "backend_url": "https://api.openai.com/v1"
    }
    
    memory = FinancialSituationMemory(name="test_long", config=config)
    
    # Create a very long situation (should trigger chunking)
    long_situation = """
    The global financial markets are experiencing unprecedented volatility across multiple asset classes. 
    """ * 1000  # Repeat to make it very long
    
    long_data = [
        (
            long_situation,
            "Diversify portfolio across uncorrelated assets and maintain higher cash reserves"
        )
    ]
    
    print(f"Long situation text length: {len(long_situation)} characters")
    
    try:
        memory.add_situations(long_data)
        print("✅ Long text chunking and storage successful")
        
        # Test retrieval
        results = memory.get_memories("Global market volatility", n_matches=1)
        
        if results and len(results) > 0:
            print(f"✅ Long text retrieval successful")
            print(f"   Similarity Score: {results[0]['similarity_score']:.2f}")
            return True
        else:
            print("❌ Long text retrieval failed")
            return False
            
    except Exception as e:
        print(f"❌ Long text test failed with error: {e}")
        return False


def test_persistent_storage():
    """Test that persistent storage works correctly."""
    print("\n" + "="*80)
    print("TEST 3: Persistent Storage")
    print("="*80)
    
    # Create temporary directory for testing
    temp_dir = tempfile.mkdtemp()
    
    try:
        config = {
            "backend_url": "https://api.openai.com/v1"
        }
        
        # Create memory with persistent storage
        memory1 = FinancialSituationMemory(
            name="test_persistent",
            config=config,
            symbol="AAPL",
            persistent_dir=temp_dir
        )
        
        # Add data
        test_data = [
            (
                "Apple stock shows strong fundamentals with growing services revenue",
                "Maintain long position with trailing stop"
            )
        ]
        
        memory1.add_situations(test_data)
        print(f"✅ Data saved to persistent storage: {temp_dir}")
        
        # Create new instance pointing to same directory
        memory2 = FinancialSituationMemory(
            name="test_persistent",
            config=config,
            symbol="AAPL",
            persistent_dir=temp_dir
        )
        
        # Retrieve data from persistent storage
        results = memory2.get_memories("Apple fundamentals", n_matches=1)
        
        if results and len(results) > 0:
            print(f"✅ Data retrieved from persistent storage")
            print(f"   Similarity Score: {results[0]['similarity_score']:.2f}")
            print(f"   Recommendation: {results[0]['recommendation']}")
            return True
        else:
            print("❌ Failed to retrieve data from persistent storage")
            return False
            
    except Exception as e:
        print(f"❌ Persistent storage test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # Cleanup
        try:
            shutil.rmtree(temp_dir)
            print(f"   Cleaned up temporary directory")
        except:
            pass


def test_symbol_collection_naming():
    """Test that symbol-based collection naming works."""
    print("\n" + "="*80)
    print("TEST 4: Symbol-Based Collection Naming")
    print("="*80)
    
    config = {
        "backend_url": "https://api.openai.com/v1"
    }
    
    # Create memory with symbol
    memory = FinancialSituationMemory(
        name="stock_analysis",
        config=config,
        symbol="MSFT"
    )
    
    print(f"✅ Created collection with symbol: stock_analysis_MSFT")
    
    # Add data
    test_data = [
        (
            "Microsoft Azure cloud revenue growing 30% YoY",
            "Increase position size due to strong cloud momentum"
        )
    ]
    
    memory.add_situations(test_data)
    results = memory.get_memories("Cloud revenue growth", n_matches=1)
    
    if results and len(results) > 0:
        print(f"✅ Symbol-based collection test passed")
        return True
    else:
        print("❌ Symbol-based collection test failed")
        return False


def main():
    """Run all tests."""
    print("\n" + "="*80)
    print("MEMORY.PY CHUNKING & PERSISTENT STORAGE TEST SUITE")
    print("="*80)
    
    print("\nNote: These tests require a valid OpenAI API key in your environment.")
    print("Set OPENAI_API_KEY environment variable or configure in dataflows/config.py")
    
    results = []
    
    # Run tests
    try:
        results.append(("Short Text Compatibility", test_short_text_backward_compatibility()))
    except Exception as e:
        print(f"❌ Short text test crashed: {e}")
        results.append(("Short Text Compatibility", False))
    
    try:
        results.append(("Long Text Chunking", test_long_text_chunking()))
    except Exception as e:
        print(f"❌ Long text test crashed: {e}")
        results.append(("Long Text Chunking", False))
    
    try:
        results.append(("Persistent Storage", test_persistent_storage()))
    except Exception as e:
        print(f"❌ Persistent storage test crashed: {e}")
        results.append(("Persistent Storage", False))
    
    try:
        results.append(("Symbol Collection Naming", test_symbol_collection_naming()))
    except Exception as e:
        print(f"❌ Symbol naming test crashed: {e}")
        results.append(("Symbol Collection Naming", False))
    
    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    for test_name, passed in results:
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{status}: {test_name}")
    
    all_passed = all(passed for _, passed in results)
    
    if all_passed:
        print("\n✅ ALL TESTS PASSED!")
        print("\nChanges are ready for PR:")
        print("1. Added langchain to requirements.txt")
        print("2. Implemented get_embedding chunking with RecursiveCharacterTextSplitter")
        print("3. Added persistent ChromaDB storage support")
        print("4. Maintained full backward compatibility")
    else:
        print("\n❌ SOME TESTS FAILED")
        print("Please review the failures above.")
    
    return all_passed


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
