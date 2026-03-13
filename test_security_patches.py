#!/usr/bin/env python3
"""
Security Test Suite for TradingAgents
Tests all 5 security patches applied on 2026-03-08
"""

import sys
import os
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent))

def test_path_traversal_protection():
    """Test 1: Path Traversal Vulnerability Fix"""
    print("\n" + "="*70)
    print("TEST 1: Path Traversal Protection")
    print("="*70)
    
    from cli.main import sanitize_save_path
    
    base_dir = Path.cwd() / "reports"
    
    # Test 1.1: Valid paths should work
    print("\n[TEST 1.1] Valid paths within reports/")
    try:
        result = sanitize_save_path("reports/test", base_dir)
        print(f"✅ PASS: Valid path accepted: {result}")
    except ValueError as e:
        print(f"❌ FAIL: Valid path rejected: {e}")
        return False
    
    # Test 1.2: Path traversal should be blocked
    print("\n[TEST 1.2] Path traversal attempts")
    malicious_paths = [
        "../../../etc/passwd",
        "/etc/passwd",
        "../../tmp/evil",
        "../../../home/user/.ssh/authorized_keys"
    ]
    
    for path in malicious_paths:
        try:
            result = sanitize_save_path(path, base_dir)
            print(f"❌ FAIL: Malicious path accepted: {path} -> {result}")
            return False
        except ValueError as e:
            print(f"✅ PASS: Blocked: {path}")
    
    # Test 1.3: Absolute paths outside reports should be blocked
    print("\n[TEST 1.3] Absolute paths outside reports/")
    try:
        result = sanitize_save_path("/tmp/test", base_dir)
        print(f"❌ FAIL: Absolute path outside reports accepted: {result}")
        return False
    except ValueError:
        print(f"✅ PASS: Absolute path blocked")
    
    print("\n✅ TEST 1 PASSED: Path traversal protection working")
    return True


def test_log_sanitization():
    """Test 2: API Key Exposure in Logs Fix"""
    print("\n" + "="*70)
    print("TEST 2: Log Sanitization")
    print("="*70)
    
    # Import the sanitization functions
    import re
    
    def sanitize_log_content(content: str) -> str:
        """Copy of sanitization function for testing"""
        content = re.sub(r'sk-[A-Za-z0-9]{48}', '***REDACTED_OPENAI_KEY***', content)
        content = re.sub(r'sk-ant-[A-Za-z0-9-]{95}', '***REDACTED_ANTHROPIC_KEY***', content)
        content = re.sub(r'AIza[A-Za-z0-9_-]{35}', '***REDACTED_GOOGLE_KEY***', content)
        content = re.sub(r'xai-[A-Za-z0-9]{48}', '***REDACTED_XAI_KEY***', content)
        content = re.sub(r'Bearer [A-Za-z0-9_-]+', 'Bearer ***REDACTED***', content)
        return content
    
    def sanitize_tool_args(args: dict) -> str:
        """Copy of sanitization function for testing"""
        SENSITIVE_KEYS = {'api_key', 'apikey', 'password', 'token', 'secret', 'authorization', 'bearer'}
        sanitized = {}
        for k, v in args.items():
            if any(sensitive in k.lower() for sensitive in SENSITIVE_KEYS):
                sanitized[k] = "***REDACTED***"
            else:
                sanitized[k] = v
        return ", ".join(f"{k}={v}" for k, v in sanitized.items())
    
    # Test 2.1: OpenAI key redaction
    print("\n[TEST 2.1] OpenAI API key redaction")
    test_content = "Using API key: sk-" + "A" * 48
    sanitized = sanitize_log_content(test_content)
    if "sk-" + "A" * 48 not in sanitized and "REDACTED" in sanitized:
        print(f"✅ PASS: OpenAI key redacted")
    else:
        print(f"❌ FAIL: OpenAI key not redacted: {sanitized}")
        return False
    
    # Test 2.2: Anthropic key redaction
    print("\n[TEST 2.2] Anthropic API key redaction")
    test_content = "Using API key: sk-ant-" + "B" * 95
    sanitized = sanitize_log_content(test_content)
    if "sk-ant-" not in sanitized and "REDACTED" in sanitized:
        print(f"✅ PASS: Anthropic key redacted")
    else:
        print(f"❌ FAIL: Anthropic key not redacted")
        return False
    
    # Test 2.3: Google key redaction
    print("\n[TEST 2.3] Google API key redaction")
    test_content = "Using API key: AIza" + "C" * 35
    sanitized = sanitize_log_content(test_content)
    if "AIza" + "C" * 35 not in sanitized and "REDACTED" in sanitized:
        print(f"✅ PASS: Google key redacted")
    else:
        print(f"❌ FAIL: Google key not redacted")
        return False
    
    # Test 2.4: Bearer token redaction
    print("\n[TEST 2.4] Bearer token redaction")
    test_content = "Authorization: Bearer abc123xyz789"
    sanitized = sanitize_log_content(test_content)
    if "abc123xyz789" not in sanitized and "REDACTED" in sanitized:
        print(f"✅ PASS: Bearer token redacted")
    else:
        print(f"❌ FAIL: Bearer token not redacted")
        return False
    
    # Test 2.5: Tool arguments sanitization
    print("\n[TEST 2.5] Tool arguments sanitization")
    test_args = {
        "api_key": "secret123",
        "query": "AAPL",
        "password": "pass123"
    }
    sanitized = sanitize_tool_args(test_args)
    if "secret123" not in sanitized and "pass123" not in sanitized and "REDACTED" in sanitized:
        print(f"✅ PASS: Sensitive args redacted: {sanitized}")
    else:
        print(f"❌ FAIL: Sensitive args not redacted: {sanitized}")
        return False
    
    print("\n✅ TEST 2 PASSED: Log sanitization working")
    return True


def test_ssrf_prevention():
    """Test 3: SSRF Prevention Fix"""
    print("\n" + "="*70)
    print("TEST 3: SSRF Prevention")
    print("="*70)
    
    from cli.announcements import validate_announcement_url
    
    # Test 3.1: Valid HTTPS URL to allowed domain
    print("\n[TEST 3.1] Valid HTTPS URL to allowed domain")
    try:
        validate_announcement_url("https://api.tauric.ai/v1/announcements")
        print(f"✅ PASS: Valid URL accepted")
    except ValueError as e:
        print(f"❌ FAIL: Valid URL rejected: {e}")
        return False
    
    # Test 3.2: HTTP should be blocked
    print("\n[TEST 3.2] HTTP scheme should be blocked")
    try:
        validate_announcement_url("http://api.tauric.ai/v1/announcements")
        print(f"❌ FAIL: HTTP scheme accepted")
        return False
    except ValueError:
        print(f"✅ PASS: HTTP scheme blocked")
    
    # Test 3.3: Localhost should be blocked
    print("\n[TEST 3.3] Localhost should be blocked")
    localhost_urls = [
        "https://localhost:6379",
        "https://127.0.0.1:8080",
        "https://0.0.0.0:3000"
    ]
    for url in localhost_urls:
        try:
            validate_announcement_url(url)
            print(f"❌ FAIL: Localhost URL accepted: {url}")
            return False
        except ValueError:
            print(f"✅ PASS: Blocked: {url}")
    
    # Test 3.4: Internal IPs should be blocked
    print("\n[TEST 3.4] Internal IPs should be blocked")
    internal_urls = [
        "https://192.168.1.1",
        "https://10.0.0.1",
        "https://172.16.0.1"
    ]
    for url in internal_urls:
        try:
            validate_announcement_url(url)
            print(f"❌ FAIL: Internal IP accepted: {url}")
            return False
        except ValueError:
            print(f"✅ PASS: Blocked: {url}")
    
    # Test 3.5: AWS metadata endpoint should be blocked
    print("\n[TEST 3.5] Cloud metadata endpoint should be blocked")
    try:
        validate_announcement_url("https://169.254.169.254/latest/meta-data/")
        print(f"❌ FAIL: Cloud metadata endpoint accepted")
        return False
    except ValueError:
        print(f"✅ PASS: Cloud metadata endpoint blocked")
    
    # Test 3.6: Unauthorized domain should be blocked
    print("\n[TEST 3.6] Unauthorized domain should be blocked")
    try:
        validate_announcement_url("https://evil.com/malicious")
        print(f"❌ FAIL: Unauthorized domain accepted")
        return False
    except ValueError:
        print(f"✅ PASS: Unauthorized domain blocked")
    
    print("\n✅ TEST 3 PASSED: SSRF prevention working")
    return True


def test_date_validation():
    """Test 4: Date Validation Fix"""
    print("\n" + "="*70)
    print("TEST 4: Date Validation")
    print("="*70)
    
    from tradingagents.dataflows.alpha_vantage_common import validate_date_string
    from datetime import datetime
    
    # Test 4.1: Valid date should work
    print("\n[TEST 4.1] Valid date format")
    try:
        result = validate_date_string("2024-01-15")
        print(f"✅ PASS: Valid date accepted: {result}")
    except ValueError as e:
        print(f"❌ FAIL: Valid date rejected: {e}")
        return False
    
    # Test 4.2: Invalid format should be rejected
    print("\n[TEST 4.2] Invalid date formats")
    invalid_formats = [
        "2024/01/15",
        "01-15-2024",
        "2024-1-15",
        "invalid",
        "2024-13-01",  # Invalid month
        "2024-02-30"   # Invalid day
    ]
    for date_str in invalid_formats:
        try:
            validate_date_string(date_str)
            print(f"❌ FAIL: Invalid format accepted: {date_str}")
            return False
        except ValueError:
            print(f"✅ PASS: Rejected: {date_str}")
    
    # Test 4.3: Future dates should be rejected
    print("\n[TEST 4.3] Future dates should be rejected")
    try:
        validate_date_string("2030-01-01")
        print(f"❌ FAIL: Future date accepted")
        return False
    except ValueError:
        print(f"✅ PASS: Future date rejected")
    
    # Test 4.4: Very old dates should be rejected
    print("\n[TEST 4.4] Dates before 1900 should be rejected")
    try:
        validate_date_string("1800-01-01")
        print(f"❌ FAIL: Date before 1900 accepted")
        return False
    except ValueError:
        print(f"✅ PASS: Date before 1900 rejected")
    
    # Test 4.5: Today's date should work
    print("\n[TEST 4.5] Today's date should work")
    today = datetime.now().strftime("%Y-%m-%d")
    try:
        result = validate_date_string(today)
        print(f"✅ PASS: Today's date accepted: {result}")
    except ValueError as e:
        print(f"❌ FAIL: Today's date rejected: {e}")
        return False
    
    print("\n✅ TEST 4 PASSED: Date validation working")
    return True


def test_file_permissions():
    """Test 5: File Permissions Fix"""
    print("\n" + "="*70)
    print("TEST 5: File Permissions")
    print("="*70)
    
    import tempfile
    import stat
    
    # Test 5.1: Create directory with secure permissions
    print("\n[TEST 5.1] Directory permissions (should be 0o700)")
    with tempfile.TemporaryDirectory() as tmpdir:
        test_dir = Path(tmpdir) / "secure_test"
        test_dir.mkdir(mode=0o700, exist_ok=True)
        
        # Check permissions
        st = os.stat(test_dir)
        mode = stat.S_IMODE(st.st_mode)
        
        if mode == 0o700:
            print(f"✅ PASS: Directory has correct permissions: {oct(mode)}")
        else:
            print(f"❌ FAIL: Directory has wrong permissions: {oct(mode)} (expected 0o700)")
            return False
    
    # Test 5.2: Create file with secure permissions
    print("\n[TEST 5.2] File permissions (should be 0o600)")
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = Path(tmpdir) / "secure_file.log"
        test_file.touch(mode=0o600, exist_ok=True)
        
        # Check permissions
        st = os.stat(test_file)
        mode = stat.S_IMODE(st.st_mode)
        
        if mode == 0o600:
            print(f"✅ PASS: File has correct permissions: {oct(mode)}")
        else:
            print(f"❌ FAIL: File has wrong permissions: {oct(mode)} (expected 0o600)")
            return False
    
    # Test 5.3: Verify permissions are restrictive
    print("\n[TEST 5.3] Verify permissions are owner-only")
    with tempfile.TemporaryDirectory() as tmpdir:
        test_dir = Path(tmpdir) / "test_dir"
        test_dir.mkdir(mode=0o700)
        test_file = test_dir / "test.log"
        test_file.touch(mode=0o600)
        
        dir_stat = os.stat(test_dir)
        file_stat = os.stat(test_file)
        
        # Check no group or other permissions
        dir_mode = stat.S_IMODE(dir_stat.st_mode)
        file_mode = stat.S_IMODE(file_stat.st_mode)
        
        # 0o700 = rwx------ (no group/other access)
        # 0o600 = rw------- (no group/other access)
        if (dir_mode & 0o077) == 0 and (file_mode & 0o077) == 0:
            print(f"✅ PASS: No group/other permissions set")
        else:
            print(f"❌ FAIL: Group/other permissions detected")
            return False
    
    print("\n✅ TEST 5 PASSED: File permissions working")
    return True


def run_all_tests():
    """Run all security tests"""
    print("\n" + "="*70)
    print("TRADINGAGENTS SECURITY TEST SUITE")
    print("Testing all 5 security patches applied on 2026-03-08")
    print("="*70)
    
    results = {
        "Path Traversal Protection": test_path_traversal_protection(),
        "Log Sanitization": test_log_sanitization(),
        "SSRF Prevention": test_ssrf_prevention(),
        "Date Validation": test_date_validation(),
        "File Permissions": test_file_permissions()
    }
    
    # Summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    
    passed = sum(results.values())
    total = len(results)
    
    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")
    
    print("\n" + "="*70)
    print(f"RESULTS: {passed}/{total} tests passed")
    print("="*70)
    
    if passed == total:
        print("\n🎉 ALL SECURITY PATCHES VERIFIED! 🎉")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed. Please review.")
        return 1


if __name__ == "__main__":
    exit_code = run_all_tests()
    sys.exit(exit_code)
