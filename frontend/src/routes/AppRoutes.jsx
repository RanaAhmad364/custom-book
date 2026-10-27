import { lazy, Suspense } from "react";
import { Route, Routes } from "react-router-dom";

const Home = lazy(() => import("../pages/public/Home/Home.jsx"));
const ExploreBooks = lazy(() => import("../pages/public/ExploreBooks/ExploreBooks.jsx"));
const Categories = lazy(() => import("../pages/public/Categories/Categories.jsx"));
const CategoryDetails = lazy(() => import("../pages/public/Categories/CategoryDetails.jsx"));
const Collections = lazy(() => import("../pages/public/Collections/Collections.jsx"));
const CollectionDetails = lazy(() => import("../pages/public/Collections/CollectionDetails.jsx"));
const BookDetails = lazy(() => import("../pages/public/BookDetails/BookDetails.jsx"));
const CreateBook = lazy(() => import("../pages/public/BookCreation/CreateBook.jsx"));
const TemplateSelection = lazy(() => import("../pages/public/BookCreation/TemplateSelection.jsx"));
const BookSetup = lazy(() => import("../pages/public/BookCreation/BookSetup.jsx"));
const PhotoUpload = lazy(() => import("../pages/public/BookCreation/PhotoUpload.jsx"));
const CreationEditor = lazy(() => import("../pages/public/BookCreation/CreationEditor.jsx"));
const Pricing = lazy(() => import("../pages/public/Pricing/Pricing.jsx"));
const FAQ = lazy(() => import("../pages/public/FAQ/FAQ.jsx"));
const HowItWorks = lazy(() => import("../pages/public/HowItWorks/HowItWorks.jsx"));
const About = lazy(() => import("../pages/public/About/About.jsx"));
const Contact = lazy(() => import("../pages/public/Contact/Contact.jsx"));
const HelpCenter = lazy(() => import("../pages/public/HelpCenter/HelpCenter.jsx"));
const PolicyPage = lazy(() => import("../pages/public/Policies/PolicyPage.jsx"));
const NotFound = lazy(() => import("../pages/public/NotFound/NotFound.jsx"));
const Login = lazy(() => import("../pages/auth/Login.jsx"));
const Register = lazy(() => import("../pages/auth/Register.jsx"));
const ForgotPassword = lazy(() => import("../pages/auth/ForgotPassword.jsx"));
const ResetPassword = lazy(() => import("../pages/auth/ResetPassword.jsx"));
const OtpVerification = lazy(() => import("../pages/auth/OtpVerification.jsx"));
const EmailVerified = lazy(() => import("../pages/auth/EmailVerified.jsx"));
const SessionExpired = lazy(() => import("../pages/auth/SessionExpired.jsx"));
const Unauthorized = lazy(() => import("../pages/auth/Unauthorized.jsx"));
const Account = lazy(() => import("../pages/auth/Account.jsx"));
const ProtectedRoute = lazy(() => import("../features/auth/ProtectedRoute.jsx"));
const DashboardLayout = lazy(() => import("../features/dashboard/DashboardLayout.jsx"));
const DashboardHome = lazy(() => import("../pages/dashboard/DashboardHome.jsx"));
const DashboardSection = lazy(() => import("../pages/dashboard/DashboardSection.jsx"));
const PdfServiceDetails = lazy(() => import("../pages/public/PdfPurchase/PdfPurchase.jsx").then((module) => ({ default: module.PdfServiceDetails })));
const PdfOrderSummary = lazy(() => import("../pages/public/PdfPurchase/PdfPurchase.jsx").then((module) => ({ default: module.PdfOrderSummary })));
const PdfCheckout = lazy(() => import("../pages/public/PdfPurchase/PdfPurchase.jsx").then((module) => ({ default: module.PdfCheckout })));
const PdfOrderProcessing = lazy(() => import("../pages/public/PdfPurchase/PdfPurchase.jsx").then((module) => ({ default: module.PdfOrderProcessing })));
const PdfDownloadHistory = lazy(() => import("../pages/public/PdfPurchase/PdfPurchase.jsx").then((module) => ({ default: module.PdfDownloadHistory })));
const PdfDownloadDetails = lazy(() => import("../pages/public/PdfPurchase/PdfPurchase.jsx").then((module) => ({ default: module.PdfDownloadDetails })));
const PrintOrderFlow = lazy(() => import("../pages/public/PrintOrder/PrintOrder.jsx").then((module) => ({ default: module.PrintOrderFlow })));
const PrintOrderHistory = lazy(() => import("../pages/public/PrintOrder/PrintOrder.jsx").then((module) => ({ default: module.PrintOrderHistory })));
const PrintOrderResult = lazy(() => import("../pages/public/PrintOrder/PrintOrder.jsx").then((module) => ({ default: module.PrintOrderResult })));
const AdminRoute = lazy(() => import("../features/admin/AdminRoute.jsx"));
const AdminLayout = lazy(() => import("../features/admin/AdminLayout.jsx"));
const AdminSection = lazy(() => import("../features/admin/AdminSection.jsx"));
const AdminDashboardPage = lazy(() => import("../features/admin/pages/AdminDashboardPage.jsx"));
const AdminPurchasesPage = lazy(() => import("../features/admin/pages/AdminPurchasesPage.jsx"));
const AdminDownloadsPage = lazy(() => import("../features/admin/pages/AdminDownloadsPage.jsx"));
const AdminBooksPage = lazy(() => import("../features/admin/pages/AdminBooksPage.jsx"));
const AdminCategoriesPage = lazy(() => import("../features/admin/pages/AdminCategoriesPage.jsx"));
const AdminCollectionsPage = lazy(() => import("../features/admin/pages/AdminCollectionsPage.jsx"));
const AdminTemplatesPage = lazy(() => import("../features/admin/pages/AdminTemplatesPage.jsx"));
const AdminPricingPage = lazy(() => import("../features/admin/pages/AdminPricingPage.jsx"));
const AdminUsersPage = lazy(() => import("../features/admin/pages/AdminUsersPage.jsx"));
const AdminPaymentsPage = lazy(() => import("../features/admin/pages/AdminPaymentsPage.jsx"));
const AdminRefundsPage = lazy(() => import("../features/admin/pages/AdminRefundsPage.jsx"));
const AdminShippingPage = lazy(() => import("../features/admin/pages/AdminShippingPage.jsx"));
const AdminNotificationsPage = lazy(() => import("../features/admin/pages/AdminNotificationsPage.jsx"));
const AdminSupportPage = lazy(() => import("../features/admin/pages/AdminSupportPage.jsx"));
const AdminReportsPage = lazy(() => import("../features/admin/pages/AdminReportsPage.jsx"));
const AdminSettingsPage = lazy(() => import("../features/admin/pages/AdminSettingsPage.jsx"));
const AdminProfilePage = lazy(() => import("../features/admin/pages/AdminProfilePage.jsx"));

export default function AppRoutes() {
  return (
    <Suspense fallback={<div className="route-loading" role="status">Loading MemoryBook…</div>}>
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="/books" element={<ExploreBooks />} />
      <Route path="/categories" element={<Categories />} />
      <Route path="/categories/:categorySlug" element={<CategoryDetails />} />
      <Route path="/books/:bookId" element={<BookDetails />} />
      <Route path="/create" element={<CreateBook />} />
      <Route path="/create/templates" element={<TemplateSelection />} />
      <Route path="/create/setup" element={<BookSetup />} />
      <Route path="/create/photos" element={<PhotoUpload />} />
      <Route path="/create/:bookId" element={<BookSetup />} />
      <Route path="/collections" element={<Collections />} />
      <Route path="/collections/:collectionSlug" element={<CollectionDetails />} />
      <Route path="/pricing" element={<Pricing />} />
      <Route path="/faq" element={<FAQ />} />
      <Route path="/how-it-works" element={<HowItWorks />} />
      <Route path="/about" element={<About />} />
      <Route path="/contact" element={<Contact />} />
      <Route path="/help" element={<HelpCenter />} />
      <Route path="/privacy" element={<PolicyPage policyKey="privacy" />} />
      <Route path="/terms" element={<PolicyPage policyKey="terms" />} />
      <Route path="/shipping" element={<PolicyPage policyKey="shipping" />} />
      <Route path="/refunds" element={<PolicyPage policyKey="refunds" />} />
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route path="/forgot-password" element={<ForgotPassword />} />
      <Route path="/reset-password" element={<ResetPassword />} />
      <Route path="/verify-otp" element={<OtpVerification />} />
      <Route path="/email-verified" element={<EmailVerified />} />
      <Route path="/session-expired" element={<SessionExpired />} />
      <Route path="/unauthorized" element={<Unauthorized />} />
      <Route element={<AdminRoute />}>
        <Route path="/admin/books/:bookId/design" element={<CreationEditor adminMode />} />
        <Route path="/admin" element={<AdminLayout />}>
          <Route index element={<AdminDashboardPage />} />
          <Route path="purchases" element={<AdminPurchasesPage />} />
          <Route path="downloads" element={<AdminDownloadsPage />} />
          <Route path="books" element={<AdminBooksPage />} />
          <Route path="categories" element={<AdminCategoriesPage />} />
          <Route path="collections" element={<AdminCollectionsPage />} />
          <Route path="templates" element={<AdminTemplatesPage />} />
          <Route path="pricing" element={<AdminPricingPage />} />
          <Route path="users" element={<AdminUsersPage />} />
          <Route path="payments" element={<AdminPaymentsPage />} />
          <Route path="refunds" element={<AdminRefundsPage />} />
          <Route path="shipping" element={<AdminShippingPage />} />
          <Route path="notifications" element={<AdminNotificationsPage />} />
          <Route path="support" element={<AdminSupportPage />} />
          <Route path="reports" element={<AdminReportsPage />} />
          <Route path="settings" element={<AdminSettingsPage />} />
          <Route path="profile" element={<AdminProfilePage />} />
          <Route path=":section" element={<AdminSection />} />
        </Route>
      </Route>
      <Route element={<ProtectedRoute />}>
        <Route path="/account" element={<Account />} />
        <Route path="/create/design/:projectId" element={<CreationEditor />} />
        <Route path="/create/design/:projectId/pdf" element={<PdfServiceDetails />} />
        <Route path="/create/design/:projectId/pdf/summary" element={<PdfOrderSummary />} />
        <Route path="/create/design/:projectId/pdf/checkout" element={<PdfCheckout />} />
        <Route path="/pdf/orders/:orderId/processing" element={<PdfOrderProcessing />} />
        <Route path="/pdf/downloads" element={<PdfDownloadHistory />} />
        <Route path="/pdf/downloads/:downloadId" element={<PdfDownloadDetails />} />
        <Route path="/create/design/:projectId/print/*" element={<PrintOrderFlow />} />
        <Route path="/print/orders" element={<PrintOrderHistory />} />
        <Route path="/print/orders/:orderId/*" element={<PrintOrderResult />} />
        <Route path="/dashboard" element={<DashboardLayout />}>
          <Route index element={<DashboardHome />} />
          <Route path="projects" element={<DashboardSection section="projects" />} />
          <Route path="recent" element={<DashboardSection section="recent" />} />
          <Route path="drafts" element={<DashboardSection section="drafts" />} />
          <Route path="completed" element={<DashboardSection section="completed" />} />
          <Route path="favorites" element={<DashboardSection section="favorites" />} />
          <Route path="downloads" element={<DashboardSection section="downloads" />} />
          <Route path="downloads/:downloadId" element={<DashboardSection section="download-detail" />} />
          <Route path="orders" element={<DashboardSection section="orders" />} />
          <Route path="orders/:orderId" element={<DashboardSection section="order-detail" />} />
          <Route path="orders/:orderId/tracking" element={<DashboardSection section="order-detail" />} />
          <Route path="notifications" element={<DashboardSection section="notifications" />} />
          <Route path="profile" element={<DashboardSection section="profile" />} />
          <Route path="settings" element={<DashboardSection section="settings" />} />
          <Route path="billing" element={<DashboardSection section="billing" />} />
          <Route path="addresses" element={<DashboardSection section="addresses" />} />
          <Route path="support" element={<DashboardSection section="support" />} />
        </Route>
      </Route>
      <Route path="*" element={<NotFound />} />
    </Routes>
    </Suspense>
  );
}
