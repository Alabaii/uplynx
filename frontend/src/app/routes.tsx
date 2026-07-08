import React from 'react';
import { createBrowserRouter, Navigate } from 'react-router';
import { AppLayout } from './layouts/AppLayout';
import { MetaProvider } from './meta-context';
import { hasValidSession } from './auth';

const AuthPage = React.lazy(() => import('./pages/Auth'));
const Dashboard = React.lazy(() => import('./pages/Dashboard'));
const AddMonitor = React.lazy(() => import('./pages/AddMonitor'));
const MonitorDetails = React.lazy(() => import('./pages/MonitorDetails'));
const History = React.lazy(() => import('./pages/History'));
const ConfigEditor = React.lazy(() => import('./pages/ConfigEditor'));
const TelegramSettings = React.lazy(() => import('./pages/Telegram'));
const Team = React.lazy(() => import('./pages/Team'));
const StatusPage = React.lazy(() => import('./pages/StatusPage'));

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
    return <Navigate to="/login" replace />;
  }

  return <>{children}</>;
}

export const router = createBrowserRouter([
  { path: '/login', element: withSuspense(<AuthPage />) },
  { path: '/register', element: withSuspense(<AuthPage />) },
  { path: '/status/:slug', element: withSuspense(<StatusPage />) },
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
      { path: 'monitors/new', element: withSuspense(<AddMonitor />) },
      { path: 'monitors/:id', element: withSuspense(<MonitorDetails />) },
      { path: 'monitors/:id/history', element: withSuspense(<History />) },
      { path: 'config', element: withSuspense(<ConfigEditor />) },
      { path: 'telegram', element: withSuspense(<TelegramSettings />) },
      { path: 'team', element: withSuspense(<Team />) },
      { path: '*', element: <Navigate to="/" replace /> },
    ],
  },
]);
