# AskHype - Frontend MVP

A mobile-first Progressive Web App (PWA) for discovering entertainment, tourism, events, and lifestyle recommendations across the Balkans.

## Quick Start

### Installation

```bash
npm install
```

### Development Server

```bash
npm run dev
```

The app will be available at `http://localhost:5173/`

For the chat screen to call the local FastAPI mock backend, also run the backend server from `backend/`.

### Build for Production

```bash
npm run build
```

### Preview Production Build

```bash
npm run preview
```

## Features

### Mobile-First Design
- Optimized for mobile devices with touch-friendly interface
- Fixed bottom navigation with central "Pitaj" action button
- Responsive desktop layout as secondary target
- Safe area support for notched devices
- PWA-ready for home screen installation

### Design System
- **Colors:**
  - Dark Navy (#0f172a) - Primary
  - Bright Yellow (#fcd34d) - Accent
  - White (#ffffff) - Background
  - Light Gray (#f1f5f9, #e5e7eb) - Secondary backgrounds
- **Typography:** System fonts for optimal performance
- **Components:** Rounded cards and buttons for modern aesthetic
- **Accessibility:** Semantic HTML with ARIA labels

## Routes

| Route | Page | Description |
|-------|------|-------------|
| `/` | Home | Main landing page with quick prompts and featured content |
| `/chat` | Chat | AI conversation interface with recommendations |
| `/explore` | Explore | Search, filter, and browse all content |
| `/recommendations/:id` | Detail | Individual item details with actions |
| `/saved` | Saved | Bookmarked items organized by category |
| `/profile` | Profile | User preferences and settings |
| `/auth` | Auth | Supabase email/password login and signup |
| `/premium` | Premium | Mock upgrade page for quota/paywall flows |

## Project Structure

```
src/
├── components/          # Reusable UI components
│   ├── AppHeader.tsx
│   ├── BottomNavigation.tsx
│   ├── AskHypeInput.tsx
│   ├── QuickPromptChip.tsx
│   ├── CategoryCircle.tsx
│   ├── RecommendationCard.tsx
│   ├── HypeContentCard.tsx
│   ├── SourceVerification.tsx
│   ├── EmptyState.tsx
│   ├── FilterChip.tsx
│   └── index.ts
├── pages/               # Page components
│   ├── HomePage.tsx
│   ├── ChatPage.tsx
│   ├── ExplorePage.tsx
│   ├── RecommendationDetailPage.tsx
│   ├── SavedPage.tsx
│   ├── ProfilePage.tsx
│   └── index.ts
├── types.ts             # TypeScript definitions
├── mock-data.ts         # Mock data
├── utils.ts             # Utilities
├── router.tsx           # React Router config
├── App.tsx              # Main app
├── index.css            # Global styles
└── main.tsx             # Entry point

public/
├── manifest.json        # PWA manifest
├── pwa-*.png           # PWA icons

index.html              # HTML entry point
```

## Local Full-Stack Development

AskHype includes a FastAPI backend under `backend/`. The Chat page calls the backend mock chat endpoint; `AI_PROVIDER` is still `mock`, and no external AI API is used.

Create frontend environment configuration from the repository root:

```bash
cp .env.example .env
```

Frontend API variable:

```bash
VITE_API_BASE_URL=http://localhost:8000
VITE_SUPABASE_URL=https://your-project.supabase.co
VITE_SUPABASE_PUBLISHABLE_KEY=your-publishable-key
```

Vercel must also define `VITE_SUPABASE_URL` and `VITE_SUPABASE_PUBLISHABLE_KEY` for production builds.

Start the backend from `backend/`:

```bash
python -m pip install -e ".[dev]"
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Start the frontend from the repository root:

```bash
npm run dev
```

Expected local URLs:

- Frontend: `http://localhost:5173`
- Backend: `http://localhost:8000`
- Chat API: `http://localhost:8000/api/chat`
- Usage API: `http://localhost:8000/api/usage`

## Mocked Features

### Data
- Locations: Beograd, Novi Sad, Niš, Zagreb, Sarajevo
- Events: EXIT, Belef, Dragslaff, Lake Bled Festival
- Destinations: Kalemegdan, Danube, Zemun, Plitvice Lakes
- Articles: Travel guides, dining, culture
- Categories: Music, Food, Nightlife, Culture, Outdoor, Travel

### Functionality (LocalStorage)
- Save/unsave items
- User preferences persistence
- Chat context preferences

### Authentication
- Supabase email/password signup and login
- Persistent browser session via Supabase Auth
- Profile display from `public.profiles`
- Logout from the Profile page
- Email confirmation may be required; after signup, users may need to confirm email before signing in

### Prompt Usage
- Guests use a browser-generated anonymous UUID stored in localStorage
- Signed-in users send the Supabase access token to the backend
- The backend verifies identity and enforces guest, free, and premium prompt quotas
- Chat shows the current usage count and a paywall notice when `/api/chat` returns `prompt_limit_reached`
- The Premium page is presentation-only; no billing provider is connected yet
- Demo Premium activation is available only when the backend says the signed-in profile is eligible

### Demo Premium
- `/premium` shows Free vs Premium, a clear demo notice, and no card fields or checkout
- Guests are sent to `/auth` with a safe return target of `/premium`
- Eligible free users can activate demo Premium after a confirmation that no charge occurs
- Eligible premium users can deactivate back to Free for repeat demo testing
- Frontend state refreshes profile and usage after activation/deactivation without a full reload
- The browser never sends plan, email, user ID, or eligibility to activate Premium

Admin allowlist step after a demo user registers:

```sql
update public.profiles
set can_activate_mock_premium = true
where user_id = '<registered-user-id>';
```

Set `MOCK_SUBSCRIPTIONS_ENABLED=false` on the backend to disable the demo endpoints. Only server-side eligibility is trusted.

### UI Mock Features
- Chat responses from the local FastAPI mock provider
- Recommendation reasoning
- Follow-up action chips

## Intentionally Excluded

### Not Implemented
- ❌ Password reset
- ❌ Magic links or social login
- ❌ Payments
- ❌ Push notifications
- ❌ Real geolocation
- ❌ Analytics

### Placeholder Systems
- 📷 Images: External placeholder service
- 🤖 AI: Local backend mock provider
- 📍 Location: Manual dropdown
- 💳 Payments: Display only Premium page; no real billing is implemented

## Tech Stack

- React 18 + TypeScript
- Vite (build tool)
- React Router v6
- Tailwind CSS 3
- vite-plugin-pwa
- lucide-react icons
- localStorage API

## Browser Support

- Modern browsers with ES2020
- iOS 13+, Android 9+
- Chrome, Firefox, Safari, Edge (latest 2 versions)

## Known Limitations

1. Images from external placeholder service
2. AI_PROVIDER is still mock
3. Manual location selection only
4. Client-side filtering only
5. No pagination
6. Basic offline fallback only

## Next Steps

1. Backend API integration
2. Real AI/LLM integration
3. Supabase setup
4. User authentication
5. Image storage
6. Real geolocation
7. Testing suite
8. CI/CD pipeline
9. Performance optimization
10. Analytics

## Development

```bash
npm run dev      # Development server
npm run build    # Production build
npm run preview  # Preview build
```

## Status

**Sprint 1 Complete:** Frontend shell with all UI pages, components, routing, mock data, and localStorage persistence.

---

**Last Updated:** July 25, 2024
