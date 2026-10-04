import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom';
import {
  HomePage,
  ExplorePage,
  RecommendationDetailPage,
  SavedPage,
  ProfilePage,
  AuthPage,
  PremiumPage,
} from './pages';
import { BottomNavigation } from './components';

export const Router = () => {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/chat" element={<Navigate to="/" replace />} />
        <Route path="/explore" element={<ExplorePage />} />
        <Route path="/recommendations/:id" element={<RecommendationDetailPage />} />
        <Route path="/saved" element={<SavedPage />} />
        <Route path="/profile" element={<ProfilePage />} />
        <Route path="/auth" element={<AuthPage />} />
        <Route path="/premium" element={<PremiumPage />} />
      </Routes>
      <LegacyBottomNavigation />
    </BrowserRouter>
  );
};

const LegacyBottomNavigation = () => {
  const { pathname } = useLocation();
  return pathname === '/' || pathname === '/chat' ? null : <BottomNavigation />;
};

export default Router;
