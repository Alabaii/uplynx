import React from 'react';
import { createBrowserRouter, Navigate } from 'react-router';
import { AppLayout } from './layouts/AppLayout';
import { PublicLayout } from './layouts/PublicLayout';
import { MetaProvider } from './meta-context';
import { hasValidSession } from './auth';

const AuthPage = React.lazy(() => import('./pages/Auth'));
const ForgotPasswordPage = React.lazy(() => import('./pages/ForgotPassword'));
const ResetPasswordPage = React.lazy(() => import('./pages/ResetPassword'));
const VerifyEmailPage = React.lazy(() => import('./pages/VerifyEmail'));
const Dashboard = React.lazy(() => import('./pages/Dashboard'));
const AddMonitor = React.lazy(() => import('./pages/AddMonitor'));
const MonitorDetails = React.lazy(() => import('./pages/MonitorDetails'));
const History = React.lazy(() => import('./pages/History'));
const Incidents = React.lazy(() => import('./pages/Incidents'));
const Maintenance = React.lazy(() => import('./pages/Maintenance'));
const ConfigEditor = React.lazy(() => import('./pages/ConfigEditor'));
const TelegramSettings = React.lazy(() => import('./pages/Telegram'));
const Team = React.lazy(() => import('./pages/Team'));
const StatusPage = React.lazy(() => import('./pages/StatusPage'));
const Admin = React.lazy(() => import('./pages/Admin'));
const Landing = React.lazy(() => import('./pages/Landing'));
const Pricing = React.lazy(() => import('./pages/Pricing'));
const Legal = React.lazy(() => import('./pages/Legal'));
const Contacts = React.lazy(() => import('./pages/Contacts'));

const PageLoader = () => (
  <div className="flex min-h-[16rem] items-center justify-center rounded-lg bg-card text-sm text-placeholder shadow-card">
    Loading workspace...
  </div>
);

const withSuspense = (children: React.ReactNode) => (
  <React.Suspense fallback={<PageLoader />}>{children}</React.Suspense>
);

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  if (!hasValidSession()) {
    // гость с корня и защищённых страниц попадает на публичный лендинг
    return <Navigate to="/welcome" replace />;
  }

  return <>{children}</>;
}

export const router = createBrowserRouter([
  { path: '/login', element: withSuspense(<AuthPage />) },
  { path: '/register', element: withSuspense(<AuthPage />) },
  { path: '/forgot-password', element: withSuspense(<ForgotPasswordPage />) },
  { path: '/reset-password', element: withSuspense(<ResetPasswordPage />) },
  { path: '/verify-email', element: withSuspense(<VerifyEmailPage />) },
  { path: '/status/:slug', element: withSuspense(<StatusPage />) },
  {
    // публичный сайт: лендинг, тарифы, юридика, контакты (требование модерации ЮKassa)
    element: <PublicLayout />,
    children: [
      { path: '/welcome', element: withSuspense(<Landing />) },
      { path: '/pricing', element: withSuspense(<Pricing />) },
      { path: '/legal/:doc', element: withSuspense(<Legal />) },
      { path: '/contacts', element: withSuspense(<Contacts />) },
    ],
  },
  {
    path: '/',
    element: (
      <ProtectedRoute>
        <MetaProvider>
          <AppLayout />
        </MetaProvider>
      </ProtectedRoute>
    ),
    children: [
      { index: true, element: withSuspense(<Dashboard />) },
      { path: 'incidents', element: withSuspense(<Incidents />) },
      { path: 'maintenance', element: withSuspense(<Maintenance />) },
      { path: 'monitors/new', element: withSuspense(<AddMonitor />) },
      { path: 'monitors/:id', element: withSuspense(<MonitorDetails />) },
      { path: 'monitors/:id/history', element: withSuspense(<History />) },
      { path: 'config', element: withSuspense(<ConfigEditor />) },
      { path: 'telegram', element: withSuspense(<TelegramSettings />) },
      { path: 'team', element: withSuspense(<Team />) },
      { path: 'admin', element: withSuspense(<Admin />) },
      { path: '*', element: <Navigate to="/" replace /> },
    ],
  },
]);
