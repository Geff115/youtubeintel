# 🎥 YouTubeIntel – Professional YouTube Channel Intelligence Platform

**YouTubeIntel** is a production-grade SaaS platform for discovering and analyzing YouTube channels at scale. Built for creators, marketers, and researchers who need actionable insights from the YouTube ecosystem.

---

## 🚀 Platform Highlights

- 🔍 **Intelligent Discovery** – 6+ methods to find related YouTube channels
- 📊 **Deep Analytics** – Full metadata and performance breakdowns
- 💳 **Credit-Based SaaS** – Usage-based pricing with tiered plans
- 🔐 **Enterprise Auth** – JWT, Google OAuth, sessions, email flows
- ⚡ **Scalable Processing** – Supports 5–15M+ channels asynchronously
- 🌐 **Cloud-Ready** – Powered by Supabase, UPSTASH Redis, Resend

---

## 🏗️ Architecture Overview

                        ┌────────────────────┐
                        │   React frontend   |
                        │(Next.js 14, Vercel)│
                        └────────┬───────────┘
                                 │
                                 ▼
                        ┌────────┴──────────┐
                        │     Flask API     │
                        │(JWT + Rate Limits)│
                        └────────┬──────────┘
                                 │
                                 ▼
                        ┌────────┴──────────┐
                        │   Celery Workers  |
                        │   (Async Tasks)   |
                        └───────────────────┘

    ┌────────────────────┐     ┌────────────────────┐     ┌────────────────────┐
    │     UPSTASH        │     │   Supabase (DB)    │     │   Resend Email     │
    │     Redis          │     │   Integration      │     │   Service          │
    └────────────────────┘     └────────────────────┘     └────────────────────┘

---

## 🛠️ Tech Stack

| Layer        | Tech                                             |
|--------------|--------------------------------------------------|
| Backend      | Python 3.11+, Flask, Celery                      |
| Auth         | JWT, Google OAuth, bcrypt                        |
| DB           | Supabase PostgreSQL, optimized indexing          |
| Cache/Queue  | UPSTASH Redis (global)                           |
| Email        | Resend API (HTML verification + password reset) |
| Payments     | Korapay (African market optimized)              |
| Frontend     | Next.js 14, TypeScript, Tailwind, shadcn/ui      |
| Deployment   | Vercel, Railway/Render (pending)                 |

---

## 📊 Key Features

### 🔐 Authentication System
- Multi-auth: Email/password + Google OAuth
- HTML email verification, password reset, device sessions
- Admin dashboard with user/session management

### 💳 Credit-Based Monetization
- Freemium: 25 credits/month free
- Tiered Plans: Starter ($9), Pro ($39), Business ($129), Enterprise ($499)
- API credit tracking + Redis-backed rate limiting
- Korapay integration for local payments

### 🔍 Channel Discovery & Analytics
- Discovery Methods: SocialBlade, collaborations, content similarity
- Batch Discovery: Up to 1M+ channels
- Metadata: Subs, views, engagement, language detection
- Video Analytics: Trending performance, growth tracking
- Exports: CSV, JSON support for all datasets

---

## ⚙️ Performance Benchmarks

| Operation         | Scale         | Time          | Credits |
|------------------|---------------|---------------|---------|
| Discovery        | 1K channels   | 5–10 min      | 5       |
| Metadata         | 10K channels  | 30–60 min     | 10      |
| Video Analytics  | 5K channels   | 45–90 min     | 15      |
| Bulk Processing  | 100K channels | 2–4 hours     | 25      |
| Enterprise       | 1M+ channels  | 1–2 days      | Custom  |

---


## 🧪 API Highlights

**Auth**
```bash
POST /api/auth/signup
POST /api/auth/signin
POST /api/auth/forgot-password
GET  /api/auth/me
```

**Channel Intelligence**
```bash
POST /api/discover-channels     # 5 credits
POST /api/fetch-metadata        # 10 credits
POST /api/fetch-videos          # 15 credits
POST /api/batch-discovery       # 50 credits
```

**Dashboard & Billing**
```bash
GET  /api/stats
POST /api/purchase-credits
GET  /api/user/credits
```

## 🏁 Getting Started
```bash
# Clone repo and setup environment
git clone https://github.com/yourusername/youtubeintel.git
cd youtubeintel
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Run auth setup
python auth_setup.py

# Start server
./start_production.sh
```

## 📄 License
MIT License – Built with ❤️ to empower creators, researchers, and marketers worldwide.

## 📬 Contact & Support
* Email: support@youtubeintel.com
* GitHub: github.com/Geff115/youtubeintel