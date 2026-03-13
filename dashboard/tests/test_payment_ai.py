#!/usr/bin/env python3
"""
E2E Tests for Payment Integration & AI Configuration
"""

import requests
import json
import sys

BASE_URL = "http://127.0.0.1:19100"

def test_crypto_prices():
    """Test crypto prices endpoint"""
    print("\n📊 Testing crypto prices...")
    res = requests.get(f"{BASE_URL}/api/crypto/prices")
    assert res.ok, f"Failed: {res.text}"
    data = res.json()
    assert 'prices' in data
    assert 'SOL' in data['prices']
    assert 'BTC' in data['prices']
    assert 'ETH' in data['prices']
    assert 'USDT' in data['prices']
    assert data['prices']['USDT'] == 1.0
    print(f"   ✓ Prices: SOL=${data['prices']['SOL']:.2f}, BTC=${data['prices']['BTC']:.0f}, ETH=${data['prices']['ETH']:.2f}")
    return True


def test_crypto_checkout_solana():
    """Test Solana crypto checkout"""
    print("\n◎ Testing Solana checkout...")
    res = requests.post(f"{BASE_URL}/api/crypto/checkout", json={
        "add_on": "watermark",
        "duration_months": 1,
        "chain": "solana",
        "token": "SOL"
    })
    assert res.ok, f"Failed: {res.text}"
    data = res.json()
    assert data['chain'] == 'solana'
    assert data['token'] == 'SOL'
    assert data['amount_usd'] == 10  # $10 for watermark
    assert 'payment_address' in data
    print(f"   ✓ Created SOL payment: {data['amount_crypto']} SOL (${data['amount_usd']})")
    return True


def test_crypto_checkout_bitcoin():
    """Test Bitcoin crypto checkout"""
    print("\n₿ Testing Bitcoin checkout...")
    res = requests.post(f"{BASE_URL}/api/crypto/checkout", json={
        "add_on": "extra_chatbot",
        "duration_months": 1,
        "chain": "bitcoin",
        "token": "BTC"
    })
    assert res.ok, f"Failed: {res.text}"
    data = res.json()
    assert data['chain'] == 'bitcoin'
    assert data['token'] == 'BTC'
    assert data['amount_usd'] == 15  # $15 for extra chatbot
    print(f"   ✓ Created BTC payment: {data['amount_crypto']} BTC (${data['amount_usd']})")
    return True


def test_crypto_checkout_ethereum():
    """Test Ethereum USDT checkout"""
    print("\nΞ Testing Ethereum USDT checkout...")
    res = requests.post(f"{BASE_URL}/api/crypto/checkout", json={
        "add_on": "analytics",
        "duration_months": 1,
        "chain": "ethereum",
        "token": "USDT"
    })
    assert res.ok, f"Failed: {res.text}"
    data = res.json()
    assert data['chain'] == 'ethereum'
    assert data['token'] == 'USDT'
    assert data['amount_usd'] == 20  # $20 for analytics
    assert data['amount_crypto'] == 20  # USDT is 1:1
    print(f"   ✓ Created ETH USDT payment: {data['amount_crypto']} USDT (${data['amount_usd']})")
    return True


def test_crypto_checkout_tier():
    """Test subscription tier checkout"""
    print("\n💼 Testing Professional tier checkout...")
    res = requests.post(f"{BASE_URL}/api/crypto/checkout", json={
        "add_on": "professional",
        "duration_months": 1,
        "chain": "solana",
        "token": "USDC"
    })
    assert res.ok, f"Failed: {res.text}"
    data = res.json()
    assert data['amount_usd'] == 50  # $50 for professional
    assert data['add_on_name'] == 'Professional Tier'
    print(f"   ✓ Created tier payment: {data['amount_crypto']} USDC (${data['amount_usd']})")
    return True


def test_stripe_checkout():
    """Test Stripe checkout (should return not configured in test mode)"""
    print("\n💳 Testing Stripe checkout...")
    res = requests.post(f"{BASE_URL}/api/stripe/checkout", json={
        "add_on": "watermark",
        "duration_months": 1
    })
    # Should be 503 (not configured) or 200 (configured)
    data = res.json()
    if res.status_code == 503:
        assert 'error' in data
        print(f"   ✓ Stripe not configured (expected): {data['error']}")
    else:
        assert 'checkout_url' in data
        print(f"   ✓ Stripe checkout URL: {data['checkout_url'][:50]}...")
    return True


def test_addons_list():
    """Test addons list"""
    print("\n🛒 Testing addons list...")
    res = requests.get(f"{BASE_URL}/api/addons")
    assert res.ok, f"Failed: {res.text}"
    data = res.json()
    assert 'addons' in data
    addon_ids = [a['id'] for a in data['addons']]
    assert 'watermark' in addon_ids
    assert 'extra_chatbot' in addon_ids
    assert 'custom_icon' in addon_ids
    assert 'analytics' in addon_ids
    
    # Check prices
    prices = {a['id']: a['price_usd'] for a in data['addons']}
    assert prices['watermark'] == 10
    assert prices['extra_chatbot'] == 15
    assert prices['custom_icon'] == 5
    assert prices['analytics'] == 20
    
    print(f"   ✓ Found {len(data['addons'])} addons with correct pricing")
    return True


def test_system_keys():
    """Test system keys endpoint"""
    print("\n🔑 Testing system keys...")
    res = requests.get(f"{BASE_URL}/api/system-keys")
    assert res.ok, f"Failed: {res.text}"
    data = res.json()
    assert 'providers' in data
    assert 'hasSystemKeys' in data
    print(f"   ✓ System keys configured: {data['hasSystemKeys']}")
    if data['providers']:
        for p in data['providers']:
            print(f"      - {p['name']}: {len(p['models'])} models")
    return True


def test_models_list():
    """Test available models"""
    print("\n🤖 Testing models list...")
    res = requests.get(f"{BASE_URL}/api/models?apiType=custom")
    assert res.ok, f"Failed: {res.text}"
    data = res.json()
    assert 'models' in data
    
    model_ids = [m['id'] for m in data['models']]
    assert 'claude-sonnet' in model_ids
    assert 'gpt-4o' in model_ids
    assert 'gemini-pro' in model_ids
    
    print(f"   ✓ Found {len(data['models'])} models: {', '.join(model_ids)}")
    return True


def test_ai_config_save_load():
    """Test saving and loading AI config for a chatbot"""
    print("\n⚙️ Testing AI config save/load...")
    
    # Create a test chatbot
    res = requests.post(f"{BASE_URL}/api/widget/generate", json={
        "name": "AI Config Test Bot"
    })
    assert res.ok, f"Failed to create chatbot: {res.text}"
    chatbot_id = res.json()['widgetId']
    
    # Update AI config with custom key
    res = requests.put(f"{BASE_URL}/api/chatbots/{chatbot_id}/ai-config", json={
        "apiType": "custom",
        "modelId": "gpt-4o",
        "apiKey": "sk-test-key-abcd1234"
    })
    assert res.ok, f"Failed to update AI config: {res.text}"
    
    # Load AI config and verify
    res = requests.get(f"{BASE_URL}/api/chatbots/{chatbot_id}/ai-config")
    assert res.ok, f"Failed to load AI config: {res.text}"
    data = res.json()
    
    assert data['apiType'] == 'custom'
    assert data['modelId'] == 'gpt-4o'
    assert data['hasApiKey'] == True
    assert data['apiKeyMasked'] == 'sk-t****1234'
    
    print(f"   ✓ AI config saved and loaded correctly")
    print(f"      - API Type: {data['apiType']}")
    print(f"      - Model: {data['modelId']}")
    print(f"      - Key: {data['apiKeyMasked']}")
    
    # Clean up
    requests.delete(f"{BASE_URL}/api/chatbots/{chatbot_id}")
    return True


def test_connection_test():
    """Test API connection test endpoint"""
    print("\n🔌 Testing connection test...")
    
    # Create a test chatbot
    res = requests.post(f"{BASE_URL}/api/widget/generate", json={
        "name": "Connection Test Bot"
    })
    chatbot_id = res.json()['widgetId']
    
    # Test with internal API
    res = requests.post(f"{BASE_URL}/api/chatbots/{chatbot_id}/test-connection", json={
        "apiType": "internal",
        "modelId": "claude-sonnet"
    })
    data = res.json()
    # Should fail since no system keys are configured
    print(f"   Internal API test: {data.get('success', False)}")
    
    # Test with custom API (format validation only)
    res = requests.post(f"{BASE_URL}/api/chatbots/{chatbot_id}/test-connection", json={
        "apiType": "custom",
        "modelId": "claude-sonnet",
        "apiKey": "sk-ant-test123"
    })
    data = res.json()
    assert data['success'] == True
    print(f"   ✓ Custom API test passed: {data['message']}")
    
    # Clean up
    requests.delete(f"{BASE_URL}/api/chatbots/{chatbot_id}")
    return True


def test_chat_with_model():
    """Test chat uses configured model"""
    print("\n💬 Testing chat with configured model...")
    
    # Create a chatbot with GPT-4o config
    res = requests.post(f"{BASE_URL}/api/widget/generate", json={
        "name": "GPT-4 Chat Test"
    })
    chatbot_id = res.json()['widgetId']
    
    # Set to use GPT-4o
    requests.put(f"{BASE_URL}/api/chatbots/{chatbot_id}/ai-config", json={
        "apiType": "custom",
        "modelId": "gpt-4o",
        "apiKey": "sk-test-chat-key"
    })
    
    # Send a chat message
    res = requests.post(f"{BASE_URL}/api/chat/{chatbot_id}", json={
        "message": "Hello!",
        "sessionId": "test-session"
    })
    assert res.ok, f"Failed: {res.text}"
    data = res.json()
    
    assert data['model'] == 'gpt-4o'
    print(f"   ✓ Chat returned with model: {data['model']}")
    print(f"   ✓ Response: {data['response'][:50]}...")
    
    # Clean up
    requests.delete(f"{BASE_URL}/api/chatbots/{chatbot_id}")
    return True


def main():
    print("=" * 60)
    print("ResonantOS Dashboard - Payment & AI Config Tests")
    print("=" * 60)
    
    tests = [
        ("Crypto Prices", test_crypto_prices),
        ("Solana Checkout", test_crypto_checkout_solana),
        ("Bitcoin Checkout", test_crypto_checkout_bitcoin),
        ("Ethereum USDT Checkout", test_crypto_checkout_ethereum),
        ("Tier Checkout", test_crypto_checkout_tier),
        ("Stripe Checkout", test_stripe_checkout),
        ("Addons List", test_addons_list),
        ("System Keys", test_system_keys),
        ("Models List", test_models_list),
        ("AI Config Save/Load", test_ai_config_save_load),
        ("Connection Test", test_connection_test),
        ("Chat with Model", test_chat_with_model),
    ]
    
    passed = 0
    failed = 0
    
    for name, test_func in tests:
        try:
            if test_func():
                passed += 1
            else:
                failed += 1
                print(f"   ✗ {name} - FAILED")
        except Exception as e:
            failed += 1
            print(f"   ✗ {name} - ERROR: {e}")
    
    print("\n" + "=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)
    
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
