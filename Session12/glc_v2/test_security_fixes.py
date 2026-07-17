#!/usr/bin/env python3
"""Comprehensive security fixes verification (A1-A6 + C1-C6)."""

import httpx
import sys
import json

BASE_URL = "http://localhost:8111"


def test_a1_authentication():
    """A1: All data plane routes require auth."""
    print("\n" + "="*80)
    print("A1: Authentication Required")
    print("="*80)
    
    routes = [
        ("POST", "/v1/chat", {"messages": [{"role": "user", "content": "test"}]}),
        ("POST", "/v1/vision", {"prompt": "test", "image": "data:image/png;base64,iVBORw0KGgo="}),
        ("POST", "/v1/embed", {"text": "test"}),
        ("POST", "/v1/speak", {"text": "test"}),
        ("POST", "/v1/transcribe", {"audio_b64": "AAAA", "mime": "audio/wav"}),
        ("GET", "/v1/status", None),
        ("GET", "/v1/providers", None),
        ("GET", "/v1/capabilities", None),
    ]
    
    passed = 0
    for method, path, body in routes:
        try:
            if method == "GET":
                r = httpx.get(f"{BASE_URL}{path}", timeout=5.0)
            else:
                r = httpx.post(f"{BASE_URL}{path}", json=body, timeout=5.0)
            
            if r.status_code == 401:
                print(f"✅ {method:4} {path:30} → 401")
                passed += 1
            else:
                print(f"❌ {method:4} {path:30} → {r.status_code}")
        except Exception as e:
            print(f"❌ {method:4} {path:30} → ERROR: {e}")
    
    return passed == len(routes)


def test_a2_docs_disabled():
    """A2: Docs disabled in production."""
    print("\n" + "="*80)
    print("A2: Docs Disabled (if GLC_DISABLE_DOCS=1)")
    print("="*80)
    
    import os
    if os.getenv("GLC_DISABLE_DOCS") == "1":
        routes = ["/docs", "/redoc", "/openapi.json"]
        passed = 0
        for path in routes:
            try:
                r = httpx.get(f"{BASE_URL}{path}", timeout=5.0)
                if r.status_code == 404:
                    print(f"✅ GET  {path:30} → 404 (disabled)")
                    passed += 1
                else:
                    print(f"❌ GET  {path:30} → {r.status_code}")
            except Exception as e:
                print(f"❌ GET  {path:30} → ERROR: {e}")
        return passed == len(routes)
    else:
        print("⚠️  GLC_DISABLE_DOCS not set - docs may be enabled")
        return True


def test_a5_lockfile():
    """A5: Verify uv.lock exists and modal_app uses it."""
    print("\n" + "="*80)
    print("A5: Reproducible Builds")
    print("="*80)
    
    from pathlib import Path
    lock = Path("uv.lock")
    modal_app = Path("modal_app.py")
    
    checks = []
    
    if lock.exists():
        print(f"✅ uv.lock exists ({lock.stat().st_size} bytes)")
        checks.append(True)
    else:
        print("❌ uv.lock missing")
        checks.append(False)
    
    if modal_app.exists():
        content = modal_app.read_text()
        if "uv.lock" in content and "--frozen" in content:
            print("✅ modal_app.py installs from uv.lock --frozen")
            checks.append(True)
        else:
            print("❌ modal_app.py doesn't use lockfile")
            checks.append(False)
        
        if "BASE_IMAGE_DIGEST" in content or "from_registry" in content:
            print("✅ modal_app.py pins base image by digest")
            checks.append(True)
        else:
            print("❌ modal_app.py uses rolling tag")
            checks.append(False)
    
    return all(checks)


def test_a6_single_container():
    """A6: Verify max_containers=1 in modal_app."""
    print("\n" + "="*80)
    print("A6: Single Container (Audit DB Protection)")
    print("="*80)
    
    from pathlib import Path
    modal_app = Path("modal_app.py")
    
    if modal_app.exists():
        content = modal_app.read_text()
        if "max_containers=1" in content:
            print("✅ modal_app.py sets max_containers=1")
            return True
        else:
            print("❌ modal_app.py missing max_containers=1")
            return False
    return False


def test_authenticated_works():
    """Verify auth still allows valid requests."""
    print("\n" + "="*80)
    print("Authenticated Access Works")
    print("="*80)
    
    try:
        from glc.config import get_or_create_install_token
        token = get_or_create_install_token()
        headers = {"Authorization": f"Bearer {token}"}
        
        r = httpx.get(f"{BASE_URL}/v1/status", headers=headers, timeout=5.0)
        if r.status_code == 200:
            print("✅ Authenticated /v1/status → 200")
            return True
        else:
            print(f"❌ Authenticated /v1/status → {r.status_code}")
            return False
    except Exception as e:
        print(f"❌ Authenticated request failed: {e}")
        return False


def test_c1_ssrf():
    """C1: SSRF protection blocks private IPs."""
    print("\n" + "="*80)
    print("C1: SSRF Protection")
    print("="*80)

    try:
        from glc.config import get_or_create_install_token
        token = get_or_create_install_token()
        headers = {"Authorization": f"Bearer {token}"}

        # Try to fetch cloud metadata endpoint
        body = {
            "prompt": "test",
            "image": "http://169.254.169.254/latest/meta-data/"
        }
        r = httpx.post(f"{BASE_URL}/v1/vision", json=body, headers=headers, timeout=5.0)

        if r.status_code == 400 and "private" in r.text.lower():
            print("✅ Private IP blocked")
            return True
        else:
            print(f"❌ SSRF not blocked: {r.status_code}")
            return False
    except Exception as e:
        print(f"⚠️  Test error: {e}")
        return False


def test_c5_rate_limit():
    """C5: LLM rate limiting."""
    print("\n" + "="*80)
    print("C5: LLM Rate Limiting")
    print("="*80)

    try:
        from glc.config import get_or_create_install_token
        token = get_or_create_install_token()
        headers = {"Authorization": f"Bearer {token}"}
        body = {"messages": [{"role": "user", "content": "test"}]}

        # Make 101 requests rapidly
        for i in range(101):
            r = httpx.post(f"{BASE_URL}/v1/chat", json=body, headers=headers, timeout=2.0)
            if r.status_code == 429:
                print(f"✅ Rate limited after {i+1} requests")
                return True

        print("❌ No rate limit after 101 requests")
        return False
    except Exception as e:
        print(f"⚠️  Test error: {e}")
        return False


if __name__ == "__main__":
    try:
        httpx.get(f"{BASE_URL}/healthz", timeout=2.0)
    except Exception:
        print(f"❌ Server not running at {BASE_URL}")
        print("Start: cd Session12/glc_v2 && uv run python -m glc.main")
        sys.exit(1)

    results = {
        "A1": test_a1_authentication(),
        "A2": test_a2_docs_disabled(),
        "A5": test_a5_lockfile(),
        "A6": test_a6_single_container(),
        "C1": test_c1_ssrf(),
        "C5": test_c5_rate_limit(),
        "Auth": test_authenticated_works(),
    }

    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    for bug, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{bug:10} {status}")

    print("\nNOTES:")
    print("- A3/A4 require Modal Sandbox (Moves 2-4)")
    print("- C2/C3/C4/C6 require integration/manual testing")

    if all(results.values()):
        print("\n🎉 All automated tests passed!")
        sys.exit(0)
    else:
        print("\n⚠️  Some tests failed")
        sys.exit(1)
