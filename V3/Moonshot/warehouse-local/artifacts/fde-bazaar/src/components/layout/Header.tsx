import { Link } from 'wouter';
import { LayoutDashboard, ShoppingCart, Activity } from 'lucide-react';

export function Header() {
  return (
    <header className="sticky top-0 z-50 w-full border-b border-border/40 bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="container mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
        <div className="flex items-center gap-6">
          <Link href="/" className="flex items-center gap-2 transition-opacity hover:opacity-80">
            <div className="flex h-8 w-8 items-center justify-center rounded-md bg-primary text-primary-foreground shadow-sm">
              <ShoppingCart className="h-4 w-4" />
            </div>
            <span className="font-semibold text-sm sm:text-lg tracking-tight">Online Marketplace Place</span>
          </Link>
          
          <nav className="hidden md:flex gap-6">
            <Link 
              href="/" 
              className="text-sm font-medium text-muted-foreground transition-colors hover:text-primary"
            >
              Order History
            </Link>
            <Link 
              href="/orders/new" 
              className="text-sm font-medium text-muted-foreground transition-colors hover:text-primary"
            >
              New Order
            </Link>
          </nav>
        </div>

        <div className="flex items-center gap-4">
          <a
            href="/"
            className="flex items-center gap-2 text-sm font-medium text-muted-foreground hover:text-foreground transition-colors"
          >
            <Activity className="h-4 w-4" />
            <span>DockSight</span>
          </a>
        </div>
      </div>
    </header>
  );
}
