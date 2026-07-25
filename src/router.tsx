import { BrowserRouter, Routes, Route } from 'react-router-dom';
import {
  HomePage,
  ChatPage,
  ExplorePage,
  RecommendationDetailPage,
  SavedPage,
  ProfilePage,
} from './pages';
import { BottomNavigation } from './components';

export const Router = () => {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/chat" element={<ChatPage />} />
        <Route path="/explore" element={<ExplorePage />} />
        <Route path="/recommendations/:id" element={<RecommendationDetailPage />} />
        <Route path="/saved" element={<SavedPage />} />
        <Route path="/profile" element={<ProfilePage />} />
      </Routes>
      <BottomNavigation />
    </BrowserRouter>
  );
};

export default Router;
