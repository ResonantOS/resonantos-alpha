# Skills Panel Specification

**Date:** 2026-02-03
**Status:** Design Phase
**Priority:** HIGH - Blocks skill marketplace decisions

> ⚠️ **This is a subset of the master spec.** See `~/clawd/projects/resonantos-v3/ECONOMY_SPEC.md` for the full economy design including reputation, tokens, and DAO structure.

---

## Overview

New sidebar tab in ResonantOS Dashboard for managing skills.

## UI Components

### 1. Sidebar Tab
- New "Skills" tab in dashboard navigation

### 2. Filter Bar (Top)
Organize filters logically:
- **ALL** - Show everything
- **Essential** - Core/required skills
- **Arena** - Competition/gaming skills
- **Top Rated** - Community favorites
- **Paid** - Premium skills
- **Coming Soon** - Announced but not ready

### 3. Skill Cards (Grid)
Each skill displayed as a card with:
- **Icon** - Visual identifier
- **Name** - Skill name
- **Toggle** - On/Off switch
- **Short description** - 1-2 lines
- **"Read More"** button → Opens popup

### 4. Skill Detail Popup
When "Read More" clicked:
- Full description
- Rating display
- Rate button (if eligible)
- Installation status
- Version info

### 5. Rating System (Blockchain)
**Requirements to rate:**
- AI must have NFT identity
- Must have minimum reputation level
- Must have own gas for transaction
- NOT a smart contract we pay gas for

---

## Payment Model

### NO Stripe - Crypto Only
**Reason:** DAO model - treasury gets cut of all purchases

**Accepted tokens:** Same as Chatbot add-ons:
- SOL, USDT, USDC (Solana)
- BTC
- ETH, USDT, USDC (Ethereum)

**DAO Treasury Cut:** Finances free gas for certain smart contracts

---

## Skill Tiers

### 1. Open Source
- Fully visible code
- Free to use
- NOT NFT-gated

### 2. NFT-Gated (Free)
- Code visible
- Requires NFT to activate
- Free but gated for identity/tracking

### 3. NFT-Gated Premium (Zero Knowledge)
- Code NOT visible (Lit Protocol encryption)
- Requires NFT + payment
- Protected IP

---

## Community Submission System

### Submit a Skill
User can propose new skills with:
- Description
- GitHub repo link
- Category

### Submission Requirements (Smart Contract)
- Must have NFT identity
- Must have minimum reputation
- Must have own gas

### Approval Process
1. Community voting
2. Code scrutiny
3. Consensus reached → Added to skill list

---

## Technical Notes

- Rating transactions on-chain
- Lit Protocol for zero-knowledge premium skills
- NFT verification via existing contracts
- Reputation system integration needed

---

## Open Questions

1. What's the minimum reputation to rate?
2. What's the minimum reputation to submit?
3. DAO treasury percentage cut?
4. Which blockchain for ratings? (Solana?)
5. Reputation system spec?

---

## Implementation Order

1. [ ] Basic Skills tab with list view
2. [ ] Filter bar
3. [ ] Skill cards with toggle
4. [ ] Detail popup
5. [ ] NFT verification integration
6. [ ] Rating system (blockchain)
7. [ ] Payment integration (crypto)
8. [ ] Community submission form
9. [ ] Voting/approval system
