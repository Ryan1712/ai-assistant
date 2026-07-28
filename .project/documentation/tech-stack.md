# Tech Stack: AI Assistant — Sprint CR-1 (Crash Reporting & Error Resilience)

**Author**: CTO - X Company
**Date**: 2026-07-27
**Status**: APPROVED — stack đã tồn tại, sprint này chỉ THÊM 3 thư viện

> ⚠️ Đây là repo đang chạy production. Stack bên dưới là **hiện trạng**, không phải lựa chọn mới.
> Chi tiết kiến trúc phần crash reporting → `.project/documentation/architecture.md`.

---

## Stack Summary

| Layer | Technology | Version | Ghi chú |
|-------|-----------|---------|---------|
| Mobile FE | Expo / React Native | SDK 57 / RN 0.86 | Đã có. React 19.2.3, `expo-dev-client` |
| Language FE | TypeScript | 6.0.3 | Đã có |
| Navigation | React Navigation | v7 | Đã có (native-stack + drawer + tabs) |
| Backend | Python + FastAPI | 3.12 / 0.115 | Đã có |
| ORM | SQLAlchemy async + asyncpg | 2.0 / 0.29 | Đã có |
| Migration | Alembic | 1.x | Đã có |
| Database | PostgreSQL | dev host port **5435** | Đã có |
| Cache / Queue | Redis + arq | 5.x / 0.26 | Đã có — dùng cho rate-limit crash log |
| Auth | JWT Bearer + refresh token | - | Đã có (`app/security.py`, `deps.get_current_user`) |
| Deployment | GitHub Actions → GHCR → VPS | - | Đã có (`.github/workflows`) |

### 🆕 THÊM MỚI trong sprint này (chỉ 3)

| Package | Vị trí | Lý do | Rủi ro |
|---------|--------|-------|--------|
| `@sentry/react-native` | frontend deps | Bắt **native crash** — ErrorBoundary không làm được | Cần build lại dev-client; tắt sạch nếu thiếu `EXPO_PUBLIC_SENTRY_DSN` |
| `jest-expo` + `@testing-library/react-native` + `react-test-renderer` | frontend devDeps | FE hiện **không có test nào**; tính năng chống crash mà không test thì không chứng minh được | devDependency, không vào bundle production |
| *(không thêm gì ở backend)* | - | pytest/SQLAlchemy/Redis đã đủ | - |

---

## Frontend Stack

### Core
- **Framework**: [Next.js 14+ / React 18+ / Vue 3]
- **Language**: TypeScript 5.x
- **Styling**: [TailwindCSS / CSS Modules / Styled Components]
- **State Management**: [Zustand / Redux / React Context]
- **Data Fetching**: [TanStack Query / SWR / RTK Query]

### UI Components
- **Component Library**: [shadcn/ui / MUI / Ant Design / Custom]
- **Icons**: [Lucide / Heroicons / FontAwesome]
- **Animations**: [Framer Motion / CSS Transitions]

### Build & Dev
- **Bundler**: [Vite / Turbopack / Webpack]
- **Linting**: ESLint + Prettier
- **Testing**: [Jest / Vitest] + [Playwright / Cypress]

---

## Backend Stack

### Core
- **Runtime**: [Node.js 20+ / Python 3.11+ / Go 1.21+]
- **Framework**: [Express / FastAPI / Gin / Spring Boot]
- **Language**: [TypeScript / Python / Go / Java]

### Database
- **Primary**: [PostgreSQL 16 / MongoDB 7 / MySQL 8]
- **ORM/ODM**: [Prisma / TypeORM / SQLAlchemy / Mongoose]
- **Migrations**: [Prisma Migrate / Alembic / golang-migrate]

### Caching & Queues
- **Cache**: [Redis 7 / Memcached]
- **Message Queue**: [BullMQ / RabbitMQ / SQS]
- **Background Jobs**: [BullMQ / Celery / Temporal]

### Authentication
- **Strategy**: [JWT + Refresh Tokens / OAuth2 / Session]
- **Library**: [NextAuth.js / Passport.js / FastAPI Security]
- **Password Hashing**: [bcrypt / Argon2]

---

## Infrastructure

### Cloud Provider
- **Primary**: [AWS / GCP / Azure / Vercel]
- **Region**: [us-east-1 / ap-southeast-1]
- **Multi-AZ**: [Yes / No]

### Deployment
- **Container**: [Docker / Podman]
- **Orchestration**: [Kubernetes / ECS / Cloud Run]
- **CI/CD**: [GitHub Actions / GitLab CI / CircleCI]

### Monitoring
- **APM**: [DataDog / New Relic / Sentry]
- **Logging**: [CloudWatch / Loki / ELK]
- **Metrics**: [Prometheus + Grafana / CloudWatch]

---

## Third-Party Services

| Service | Provider | Purpose |
|---------|----------|---------|
| Email | [SendGrid / Resend / SES] | Transactional emails |
| Storage | [S3 / Cloudflare R2 / GCS] | File uploads |
| CDN | [CloudFront / Cloudflare] | Static assets |
| Payments | [Stripe / PayPal] | Payment processing |
| Analytics | [Mixpanel / PostHog / GA4] | Product analytics |

---

## Development Setup

### Prerequisites
```bash
node >= 20.0.0
npm >= 10.0.0
docker >= 24.0.0
```

### Local Development
```bash
# Clone and install
git clone [repo-url]
npm install

# Environment
cp .env.example .env.local

# Database
docker-compose up -d
npx prisma db push

# Run
npm run dev
```

---

## Stack Decisions (ADRs)

### ADR-001: [Decision Title]
- **Date**: [DATE]
- **Status**: Accepted
- **Context**: [Why decision needed]
- **Decision**: [What was decided]
- **Consequences**: [Trade-offs]

---

**Approved By**: [CTO Name]
**Review Date**: [DATE]
