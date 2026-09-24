import { type ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ErrorBoundary } from '@/components/error-boundary';
import { Toaster } from '@/components/ui/toaster';
import { TooltipProvider } from '@/components/ui/tooltip';
import NotFound from '@/pages/not-found';
import {
  Route,
  Switch,
  useLocation,
  Router as WouterRouter,
} from 'wouter';

import { Header } from '@/components/layout/Header';
import Overview from '@/pages/Overview';
import NewOrder from '@/pages/NewOrder';
import Receipt from '@/pages/Receipt';

const queryClient = new QueryClient();

function Router() {
  return (
    <div className="min-h-[100dvh] flex flex-col bg-background font-sans text-foreground">
      <Header />
      <main className="flex-1">
        <RoutedErrorBoundary>
          <Switch>
            <Route path="/" component={Overview} />
            <Route path="/orders/new" component={NewOrder} />
            <Route path="/orders/:id" component={Receipt} />
            <Route component={NotFound} />
          </Switch>
        </RoutedErrorBoundary>
      </main>
    </div>
  );
}

function RoutedErrorBoundary({ children }: { children: ReactNode }) {
  const [location] = useLocation();
  return <ErrorBoundary resetKey={location}>{children}</ErrorBoundary>;
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <WouterRouter base={import.meta.env.BASE_URL.replace(/\/$/, '')}>
          <Router />
        </WouterRouter>
        <Toaster />
      </TooltipProvider>
    </QueryClientProvider>
  );
}

export default App;
