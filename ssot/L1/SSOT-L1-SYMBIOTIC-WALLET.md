# Symbiotic Wallet — Architecture & Access Model

**Level:** L1 (Architecture — Truth)  
**Created:** 2026-02-20  
**Status:** Active  
**Stale After:** Never (core architecture)

---

## Core Principle

**The Symbiotic Wallet is the ONLY gateway to the DAO.** Nothing else interacts with the DAO directly.

## Three-Wallet Architecture

| Wallet | Owner | Purpose | DAO Access |
|--------|-------|---------|------------|
| **Human Wallet** (Phantom) | Manolo | Personal operations, co-signing | ❌ No direct DAO access |
| **AI Wallet** | Augmentor | None currently | ❌ No direct DAO access |
| **Symbiotic Wallet** (PDA) | Shared (Human + AI) | ALL DAO interaction | ✅ The ONLY key to the DAO |

## Access Rules

### Symbiotic Wallet Capabilities
- Send to **any** address (no restrictions)
- Receive from **any** address (no restrictions)
- **All** DAO operations flow through it
- Interacts with other AIs, smart contracts, external parties — always through this wallet

### Human (Manolo via Phantom)
- Can do **many things independently** (personal transactions, viewing, etc.)
- **Must co-sign with AI** for: deploying smart contracts, signing contracts, governance actions
- Uses Phantom wallet for personal, Symbiotic for DAO

### AI (Augmentor)
- **Cannot act alone** — always operates **through the Symbiotic Wallet**
- Needs Symbiotic Wallet to interact with other AIs
- No independent wallet operations outside the Symbiotic Wallet

### Together (Co-signed)
- Smart contract deployment
- Contract signing
- Governance decisions
- Any high-stakes DAO operation

## Identity Rule

> If you are inside the DAO, it is because you have the Symbiotic Wallet. The Symbiotic Wallet IS your DAO identity.

### Identity NFT as Authentication Primitive (2026-02-21)

The **Identity NFT** (soulbound, non-transferable) is what makes a wallet a Symbiotic Wallet. Without it, a wallet is just a wallet.

**On-chain verification — Multi-NFT Gate (2026-02-21):**

Every smart contract that gates DAO operations must verify the **full membership stack**:

| # | Check | What it proves | ~CU cost |
|---|-------|---------------|----------|
| 1 | Identity NFT | DAO member (primary gate) | ~200 |
| 2 | Symbiotic License NFT | Signed legal agreement | ~200 |
| 3 | Manifesto NFT | Philosophical alignment | ~200 |
| 4 | $RCT balance > 0 | Active contributor | ~100 |
| 5 | $RES balance ≥ price | Can pay (for purchases) | ~100 |

**Total overhead: ~800 CU** (budget: 200,000 CU per tx). Negligible cost, maximum security.

**Rationale:** Each soulbound NFT is non-transferable — an attacker would need to complete the entire onboarding flow legitimately. Stacking checks makes the gate exponentially harder to bypass. Since the cost is marginal, always check all of them.

**Smart contract pseudocode:**
```
fn verify_dao_member(wallet) → Result:
    assert has_nft(wallet, IDENTITY_MINT)      // primary gate
    assert has_nft(wallet, LICENSE_MINT)        // legal gate
    assert has_nft(wallet, MANIFESTO_MINT)      // philosophy gate
    assert token_balance(wallet, RCT_MINT) > 0  // reputation gate
    Ok(())
```

**Implications:**
- Protocol Store: `list_protocol` and `buy_protocol` must run full `verify_dao_member()`
- Any future DAO contract: same multi-NFT check as universal auth
- $RCT threshold is part of the stack (not standalone) — proves active participation
- $RES balance check is contextual (only for purchase operations)

## Bidirectional Contract Trust (2026-02-22)

The membership stack above handles **inbound** verification (contract checks user). For **outbound** verification (user/client checks contract), see **SSOT-L1-BIDIRECTIONAL-CONTRACT-TRUST.md**.

Key points:
- DAO-approved contracts hold a **Program Identity NFT** on their PDA
- Client verifies the NFT's collection address before building transactions
- Advisory model: warns users about unverified contracts, never blocks
- Mutual authentication = both sides prove identity before interaction

## Technical Details

- **Program ID:** `HMthR7AStR3YKJ4m8GMveWx5dqY3D2g2cfnji7VdcVoG`
- **Network:** Solana DevNet
- **PDA Derivation:** Seeds define the symbiotic wallet address
- **Instructions:** `transfer_out` (SPL tokens), system transfer (SOL)
- **Client:** `solana-toolkit/symbiotic_client.py`

## Implementation Consequences

1. Dashboard wallet page: send/receive must use Symbiotic Wallet for DAO operations
2. SOL + RES are transferable via Symbiotic Wallet
3. RCT is soulbound — cannot be sent (governance only)
4. Any future AI-to-AI interaction routes through Symbiotic Wallet
5. No direct Human Wallet → DAO path exists
