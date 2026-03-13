[AI-OPTIMIZED] ~200 tokens | src: SSOT-L1-SYMBIOTIC-WALLET.md

| Field | Value |
|-------|-------|
| Level | L1 | Status | Active | Created | 2026-02-20 | Stale After | Never |

## Core Principle
**Symbiotic Wallet = ONLY gateway to the DAO.** Nothing else interacts with DAO directly.

## Three-Wallet Architecture
| Wallet | Owner | Purpose | DAO Access |
|--------|-------|---------|------------|
| Human (Phantom) | Manolo | Personal ops, co-signing | ❌ No direct |
| AI | Augmentor | None currently | ❌ No direct |
| Symbiotic (PDA) | Human+AI shared | ALL DAO interaction | ✅ Only key |

## Access Rules
- **Symbiotic:** Send/receive any address; all DAO ops; other AIs/contracts/external parties
- **Human alone:** Personal transactions; viewing; must co-sign with AI for contracts/governance/high-stakes
- **AI alone:** Cannot act; always via Symbiotic Wallet
- **Together:** Smart contract deploy, contract signing, governance decisions

## Identity Rule
> "If you are inside the DAO, it is because you have the Symbiotic Wallet. It IS your DAO identity."

## On-Chain Verification: Multi-NFT Gate (2026-02-21)
Every DAO-gating contract must verify full membership stack:
| # | Check | Proves | ~CU |
|---|-------|--------|-----|
| 1 | Identity NFT | DAO member (primary gate) | ~200 |
| 2 | Symbiotic License NFT | Signed legal agreement | ~200 |
| 3 | Manifesto NFT | Philosophical alignment | ~200 |
| 4 | $RCT balance > 0 | Active contributor | ~100 |
| 5 | $RES balance ≥ price | Can pay (purchases only) | ~100 |
**Total: ~800 CU** (budget: 200K CU/tx — negligible)

```python
fn verify_dao_member(wallet):
    assert has_nft(wallet, IDENTITY_MINT)
    assert has_nft(wallet, LICENSE_MINT)
    assert has_nft(wallet, MANIFESTO_MINT)
    assert token_balance(wallet, RCT_MINT) > 0
    Ok(())
```

## Bidirectional Contract Trust
Membership stack = inbound check (contract checks user). Outbound check (user checks contract) → see SSOT-L1-BIDIRECTIONAL-CONTRACT-TRUST.md.

## Technical Details
- **Program ID:** `HMthR7AStR3YKJ4m8GMveWx5dqY3D2g2cfnji7VdcVoG`
- **Network:** Solana DevNet
- **Client:** `solana-toolkit/symbiotic_client.py`

## Implementation Rules
1. Dashboard wallet: send/receive uses Symbiotic for DAO ops
2. SOL + RES transferable via Symbiotic
3. $RCT soulbound — cannot be sent (governance only)
4. AI-to-AI interaction routes through Symbiotic
5. No Human Wallet → DAO direct path
