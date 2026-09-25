import React from 'react';
import { AlertCircle } from 'lucide-react';
import { Link } from 'wouter';
import { Button } from '@/components/ui/button';

export default function NotFound() {
  return (
    <div className="flex flex-col items-center justify-center min-h-[50vh] space-y-4 text-center p-8 font-sans">
      <AlertCircle className="h-16 w-16 text-destructive mb-4" />
      <h1 className="text-4xl font-bold tracking-tight">404 - Not Found</h1>
      <p className="text-muted-foreground font-mono max-w-md">
        The requested inspection view does not exist or has been archived.
      </p>
      <div className="mt-8">
        <Link href="/">
          <Button variant="outline" className="font-mono">
            RETURN TO OVERVIEW
          </Button>
        </Link>
      </div>
    </div>
  );
}
