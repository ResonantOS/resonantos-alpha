# Contributing to ResonantOS

Thank you for your interest in contributing to ResonantOS! This guide will help you get started.

## 🤝 Types of Contributions

We welcome all types of contributions:

### Code
- Bug fixes
- New features (discuss in Issues first)
- Performance improvements
- Test coverage

### Documentation
- Tutorials and guides
- Installation troubleshooting
- Concept explanations
- README improvements

### Community
- Answering questions in Discord
- Writing blog posts
- Creating demos
- Sharing use cases

## 🚀 Getting Started

### Prerequisites
- Node.js 18+
- Python 3
- Git
- OpenClaw installed

### Setup

1. **Fork the repository**
   ```bash
   # Click "Fork" on GitHub, then:
   git clone https://github.com/YOUR-USERNAME/resonantos-alpha.git
   cd resonantos-alpha
   ```

2. **Add upstream remote**
   ```bash
   git remote add upstream https://github.com/ManoloRemiddi/resonantos-alpha.git
   ```

3. **Install dependencies**
   ```bash
   node install.js
   ```

## 📝 Contribution Workflow

### 1. Create a Branch

```bash
git checkout -b feature/your-feature-name
```

Branch naming conventions:
- `feature/` — New features
- `fix/` — Bug fixes
- `docs/` — Documentation
- `refactor/` — Code refactoring

### 2. Make Your Changes

- Write clear, readable code
- Follow existing code style
- Add comments for complex logic
- Update documentation as needed
- Test your changes thoroughly

### 3. Commit Your Changes

Use clear, descriptive commit messages:

```bash
git commit -m "Fix: Resolve SSoT injection bug in L2 docs"
git commit -m "Feature: Add mobile dashboard support"
git commit -m "Docs: Update installation guide for Windows"
```

Format: `<Type>: <Description>`

Types: `Fix`, `Feature`, `Docs`, `Refactor`, `Test`, `Chore`

### 4. Keep Your Fork Updated

```bash
git fetch upstream
git rebase upstream/main
```

### 5. Push to Your Fork

```bash
git push origin feature/your-feature-name
```

### 6. Open a Pull Request

- Go to your fork on GitHub
- Click "New Pull Request"
- Select your branch
- Fill out the PR template

**In your PR, please include:**
- Clear description of what changed
- Why the change was needed
- How you tested it
- Screenshots (if UI changes)
- Reference any related issues (`Fixes #123`)

### 7. Review Process

- Maintainers will review your PR
- Address any feedback or requested changes
- Once approved, a maintainer will merge

## 🤖 AI Collaboration Attribution

When working with an AI collaborator, please:

1. **Mark AI contributions in commits:**
   ```bash
   git commit -m "Feature: Add compression algorithm
   
   Co-authored-by: Augmentor <ai@resonantos.com>"
   ```

2. **Explain in PR comments:**
   - Which parts were AI-generated
   - Which parts were human-authored
   - How you reviewed/validated AI output

3. **Review all AI output before committing**
   - Understand what the code does
   - Test thoroughly
   - Take responsibility for the contribution

## 🧪 Testing

Before submitting:

- Test your changes locally
- Verify existing features still work
- Check for console errors
- Test on your target platform (macOS/Linux/Windows)

## 📖 Documentation

If your contribution changes user-facing behavior:

- Update relevant documentation
- Add examples if helpful
- Update the README if needed

## 🐛 Reporting Bugs

Use GitHub Issues with:
- Clear, descriptive title
- Steps to reproduce
- Expected vs actual behavior
- Environment details (OS, Node version, OpenClaw version)
- Error messages and logs
- Screenshots if relevant

## 💡 Suggesting Features

Before opening a feature request:
- Search existing issues to avoid duplicates
- Discuss in Discord #roadmap first for major changes
- Explain the use case and benefit

Feature requests should include:
- Clear description of the feature
- Why it's needed
- How it fits with ResonantOS philosophy
- Potential implementation approach (optional)

## 🔒 Security Issues

**DO NOT** open public issues for security vulnerabilities.

Instead:
- Email: security@resonantos.com (if configured)
- Discord DM: @ManoloRemiddi
- Include: Description, reproduction steps, potential impact

We'll respond within 48 hours.

## 📜 License

By contributing, you agree that your contributions will be licensed under the RC-SL v1.0 license (Resonant Core — Symbiotic License v1.0).

See [LICENSE](LICENSE) for details.

## 🏛️ Governance

Significant contributions earn you:
- **$RCT tokens** — Soulbound governance rights (non-transferable)
- Recognition in the community
- Potential maintainer status

Learn more about governance in our [Community Standards](COMMUNITY_STANDARDS.md).

## 💬 Questions?

- **Discord:** https://discord.gg/MRESQnf4R4
- **GitHub Discussions:** https://github.com/ManoloRemiddi/resonantos-alpha/discussions
- **Maintainer:** @ManoloRemiddi

---

Thank you for contributing to ResonantOS! Together, we're building the future of human-AI collaboration.

*"The most human thing we can do is make meaning together."*