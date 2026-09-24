import React, { useState } from 'react';
import { RecordBrowser } from '@/components/RecordBrowser';
import { useGetReviewOverview } from '@workspace/api-client-react';
import { CodeBlock } from '@/components/CodeBlock';
import { Button } from '@/components/ui/button';
import { Code2, ChevronDown, ChevronUp } from 'lucide-react';

export function Inventory() {
  const { data: overview } = useGetReviewOverview();
  const [showSource, setShowSource] = useState(false);

  return (
    <RecordBrowser 
      dataset="inventory" 
      title="Inventory Ledger" 
      description="Compare WMS, ERP, and vision system states. Focus on legacyAvailable computation anomalies." 
      headerContent={
        overview?.inventorySource && (
          <div className="border rounded-sm overflow-hidden bg-muted/10">
            <button 
              className="w-full flex items-center justify-between p-3 bg-muted/30 hover:bg-muted/50 transition-colors text-sm font-bold font-mono text-muted-foreground uppercase"
              onClick={() => setShowSource(!showSource)}
            >
              <span className="flex items-center gap-2"><Code2 className="h-4 w-4" /> Original Inventory Source Logic</span>
              {showSource ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
            </button>
            {showSource && (
              <div className="border-t">
                <CodeBlock code={overview.inventorySource} className="rounded-none border-0 max-h-[300px]" />
              </div>
            )}
          </div>
        )
      }
    />
  );
}
