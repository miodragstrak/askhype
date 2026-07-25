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
- Chat history storage

### UI Mock Features
- Chat conversations (static)
- AI responses (static templates)
- Recommendation reasoning
- Next actions (non-functional)

## Intentionally Excluded

### Not Implemented
- ❌ Backend/API
- ❌ Authentication
- ❌ Database/Supabase
- ❌ Real AI integration
- ❌ Payments
- ❌ Push notifications
- ❌ Real geolocation
- ❌ Analytics

### Placeholder Systems
- 📷 Images: External placeholder service
- 🤖 AI: Mock responses
- 📍 Location: Manual dropdown
- 💬 Chat: Non-functional UI
- 💳 Payments: Display only

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
2. Static mock AI responses
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
