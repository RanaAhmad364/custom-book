import PublicLayout from "./layouts/PublicLayout.jsx";
import AppRoutes from "./routes/AppRoutes.jsx";
import { AuthProvider } from "./features/auth/AuthContext.jsx";
import { BookCreationProvider } from "./features/bookCreation/BookCreationContext.jsx";

export default function App() {
  return (
    <AuthProvider>
      <BookCreationProvider>
        <PublicLayout>
          <AppRoutes />
        </PublicLayout>
      </BookCreationProvider>
    </AuthProvider>
  );
}
