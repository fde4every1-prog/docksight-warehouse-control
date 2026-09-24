import { useEffect, type ReactNode } from 'react';
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
  Redirect,
} from 'wouter';

import { PersonaProvider, usePersona, getPersonaHomePath } from '@/contexts/PersonaContext';
import { Layout } from '@/components/Layout';
import { Overview } from '@/pages/Overview';
import { Fleet } from '@/pages/Fleet';
import { Inventory } from '@/pages/Inventory';
import { Tasks } from '@/pages/Tasks';
import { Evidence } from '@/pages/Evidence';
import { Allocator } from '@/pages/Allocator';

import FulfillmentDashboard from '@/pages/Fulfillment/index';
import FulfillmentOrderList from '@/pages/Fulfillment/OrderList';
import FulfillmentOrderDetails from '@/pages/Fulfillment/OrderDetails';
import FulfillmentResources from '@/pages/Fulfillment/ResourceExplorer';
import FulfillmentConfig from '@/pages/Fulfillment/ConfigPanel';
import FulfillmentDemandForecasts from '@/pages/Fulfillment/DemandForecasts';
import FulfillmentReplays from '@/pages/Fulfillment/Replays';
import FulfillmentReplayDetails from '@/pages/Fulfillment/ReplayDetails';

import FleetWorkspace from '@/pages/Workspace/Fleet/index';
import SupervisorWorkspace from '@/pages/Workspace/Supervisor/index';
import AdminWorkspace from '@/pages/Workspace/Admin/index';
import InterventionDetails from '@/pages/Workspace/Interventions/InterventionDetails';

import PredictiveMaintenance from '@/pages/Fleet/PredictiveMaintenance/index';
import MonthlyKpis from '@/pages/Workspace/MonthlyKpis';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

function RouteGuard({ children, allowedRoles }: { children: ReactNode; allowedRoles?: string[] }) {
  const { role } = usePersona();
  const [location] = useLocation();
  // Apply the Admin allowlist outside the entire route switch as well as
  // individual guards, so legacy routes and direct URLs cannot bypass it.
  const adminAllowed = ['/', '/workspace/admin', '/fulfillment/resources', '/fulfillment/config']
    .includes(location.replace(/\/+$/, '') || '/');
  
  if ((role === 'admin' && !adminAllowed) || (allowedRoles && !allowedRoles.includes(role))) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center p-8 bg-background">
        <div className="max-w-md w-full bg-card border shadow-sm rounded-lg p-6 text-center">
          <div className="w-12 h-12 bg-destructive/10 text-destructive rounded-full flex items-center justify-center mx-auto mb-4">
            <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><path d="M12 9v4"/><path d="M12 17h.01"/></svg>
          </div>
          <h2 className="text-xl font-bold mb-2">Access Restricted</h2>
          <p className="text-muted-foreground mb-4">
            The {role.toUpperCase()} persona is not authorized to view this area.
          </p>
        </div>
      </div>
    );
  }
  
  return <>{children}</>;
}

function RootRedirect() {
  const { role } = usePersona();
  return <Redirect to={getPersonaHomePath(role)} />;
}

function FdeBazaarRedirect() {
  useEffect(() => {
    window.location.replace('/fde-bazaar/');
  }, []);

  return (
    <div className="flex-1 flex items-center justify-center p-8 bg-background">
      <div className="max-w-md w-full bg-card border shadow-sm rounded-lg p-6 text-center">
        <h2 className="text-xl font-bold mb-2">Opening Online Marketplace Place</h2>
        <p className="text-muted-foreground mb-4">
          New orders are created in the Online Marketplace Place application.
        </p>
      </div>
    </div>
  );
}

function Router() {
  return (
    <PersonaProvider>
      <Layout>
        <RoutedErrorBoundary>
          <RouteGuard>
          <Switch>
            <Route path="/" component={RootRedirect} />
            
            {/* Legacy Routes (Always Accessible) */}
            <Route path="/overview" component={Overview} />
            <Route path="/fleet" component={Fleet} />
            <Route path="/inventory" component={Inventory} />
            <Route path="/tasks" component={Tasks} />
            <Route path="/evidence" component={Evidence} />
            <Route path="/allocator" component={Allocator} />
            
            {/* Workspace Routes */}
            <Route path="/workspace/monthly-kpis">
              <RouteGuard allowedRoles={['fleet', 'supervisor', 'admin']}><MonthlyKpis /></RouteGuard>
            </Route>
            <Route path="/workspace/fleet">
              <RouteGuard allowedRoles={['fleet']}><FleetWorkspace /></RouteGuard>
            </Route>
            <Route path="/workspace/supervisor">
              <RouteGuard allowedRoles={['supervisor']}><SupervisorWorkspace /></RouteGuard>
            </Route>
            <Route path="/workspace/admin">
              <RouteGuard allowedRoles={['admin']}><AdminWorkspace /></RouteGuard>
            </Route>
            
            {/* Interventions (Shared but restricted inner view depending on owner) */}
            <Route path="/workspace/interventions/:id">
              {(params) => (
                <RouteGuard allowedRoles={['fleet', 'supervisor']}>
                  <InterventionDetails id={params.id!} />
                </RouteGuard>
              )}
            </Route>
            
            {/* Predictive Maintenance */}
            <Route path="/fleet/predictive-maintenance">
              <RouteGuard allowedRoles={['fleet', 'supervisor', 'admin']}><PredictiveMaintenance /></RouteGuard>
            </Route>

            {/* Supervisor Fulfillment Routes */}
            <Route path="/fulfillment">
              <RouteGuard allowedRoles={['supervisor']}><FulfillmentDashboard /></RouteGuard>
            </Route>
            <Route path="/fulfillment/orders">
              <RouteGuard allowedRoles={['supervisor']}><FulfillmentOrderList /></RouteGuard>
            </Route>
            <Route path="/fulfillment/orders/new">
              <RouteGuard allowedRoles={['supervisor']}><FdeBazaarRedirect /></RouteGuard>
            </Route>
            <Route path="/fulfillment/orders/:id">
              {() => (
                <RouteGuard allowedRoles={['fleet', 'supervisor']}>
                  <FulfillmentOrderDetails />
                </RouteGuard>
              )}
            </Route>
            
            {/* Shared Fulfillment Routes */}
            <Route path="/fulfillment/demand-forecasts">
              <RouteGuard allowedRoles={['supervisor', 'admin']}>
                <FulfillmentDemandForecasts />
              </RouteGuard>
            </Route>
            <Route path="/fulfillment/resources">
              <RouteGuard allowedRoles={['fleet', 'supervisor', 'admin']}>
                <FulfillmentResources />
              </RouteGuard>
            </Route>
            
            {/* Admin Fulfillment Routes */}
            <Route path="/fulfillment/config">
              <RouteGuard allowedRoles={['admin']}><FulfillmentConfig /></RouteGuard>
            </Route>

            <Route path="/fulfillment/replays">
              <RouteGuard allowedRoles={['supervisor', 'admin']}><FulfillmentReplays /></RouteGuard>
            </Route>
            <Route path="/fulfillment/replays/:runId/orders/:orderId">
              {(params) => (
                <RouteGuard allowedRoles={['supervisor', 'admin']}>
                  <FulfillmentReplayDetails runId={decodeURIComponent(params.runId!)} orderId={decodeURIComponent(params.orderId!)} />
                </RouteGuard>
              )}
            </Route>
            <Route path="/fulfillment/replays/:runId">
              {(params) => (
                <RouteGuard allowedRoles={['supervisor', 'admin']}>
                  <FulfillmentReplays runId={params.runId!} />
                </RouteGuard>
              )}
            </Route>

            <Route component={NotFound} />
          </Switch>
          </RouteGuard>
        </RoutedErrorBoundary>
      </Layout>
    </PersonaProvider>
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
