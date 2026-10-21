import { Route, Routes } from "react-router-dom";
import Home from "../pages/public/Home/Home.jsx";
import ExploreBooks from "../pages/public/ExploreBooks/ExploreBooks.jsx";
import Categories from "../pages/public/Categories/Categories.jsx";
import CategoryDetails from "../pages/public/Categories/CategoryDetails.jsx";
import Collections from "../pages/public/Collections/Collections.jsx";
import CollectionDetails from "../pages/public/Collections/CollectionDetails.jsx";
import BookDetails from "../pages/public/BookDetails/BookDetails.jsx";
import CreateBook from "../pages/public/BookCreation/CreateBook.jsx";
import TemplateSelection from "../pages/public/BookCreation/TemplateSelection.jsx";
import BookSetup from "../pages/public/BookCreation/BookSetup.jsx";
import PhotoUpload from "../pages/public/BookCreation/PhotoUpload.jsx";
import CreationEditor from "../pages/public/BookCreation/CreationEditor.jsx";
import Pricing from "../pages/public/Pricing/Pricing.jsx";
import FAQ from "../pages/public/FAQ/FAQ.jsx";
import HowItWorks from "../pages/public/HowItWorks/HowItWorks.jsx";
import About from "../pages/public/About/About.jsx";
import Contact from "../pages/public/Contact/Contact.jsx";
import HelpCenter from "../pages/public/HelpCenter/HelpCenter.jsx";
import PolicyPage from "../pages/public/Policies/PolicyPage.jsx";
import NotFound from "../pages/public/NotFound/NotFound.jsx";
import Login from "../pages/auth/Login.jsx";
import Register from "../pages/auth/Register.jsx";
import ForgotPassword from "../pages/auth/ForgotPassword.jsx";
import ResetPassword from "../pages/auth/ResetPassword.jsx";
import OtpVerification from "../pages/auth/OtpVerification.jsx";
import EmailVerified from "../pages/auth/EmailVerified.jsx";
import SessionExpired from "../pages/auth/SessionExpired.jsx";
import Unauthorized from "../pages/auth/Unauthorized.jsx";
import Account from "../pages/auth/Account.jsx";
import ProtectedRoute from "../features/auth/ProtectedRoute.jsx";
import DashboardLayout from "../features/dashboard/DashboardLayout.jsx";
import DashboardHome from "../pages/dashboard/DashboardHome.jsx";
import DashboardSection from "../pages/dashboard/DashboardSection.jsx";
import { PdfServiceDetails, PdfOrderSummary, PdfCheckout, PdfOrderProcessing, PdfDownloadHistory, PdfDownloadDetails } from "../pages/public/PdfPurchase/PdfPurchase.jsx";
import { PrintOrderFlow, PrintOrderHistory, PrintOrderResult } from "../pages/public/PrintOrder/PrintOrder.jsx";

export default function AppRoutes() {
  return (
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
  );
}
