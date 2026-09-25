import React, { useState } from 'react';
import { useGetReviewOverview } from '@workspace/api-client-react';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { RecordBrowser } from '@/components/RecordBrowser';
import { Mail, ShieldAlert } from 'lucide-react';

export function Evidence() {
  const { data: overview } = useGetReviewOverview();

  return (
    <div className="h-full flex flex-col font-sans">
      <div className="p-6 border-b shrink-0 bg-card">
        <h1 className="text-2xl font-bold tracking-tight">Evidence Locker</h1>
        <p className="text-muted-foreground text-sm max-w-2xl mt-1">
          Operational email notes and secondary datasets (maintenance, priorities, zones, telemetry).
        </p>
      </div>

      <div className="flex-1 flex flex-col overflow-hidden">
        <Tabs defaultValue="notes" className="flex-1 flex flex-col h-full">
          <div className="px-6 py-3 border-b bg-muted/30">
            <TabsList className="bg-transparent border p-0 h-10 w-full justify-start overflow-x-auto rounded-sm">
              <TabsTrigger value="notes" className="rounded-none data-[state=active]:bg-primary data-[state=active]:text-primary-foreground border-r last:border-r-0 font-mono text-xs px-6 h-full gap-2">
                <Mail className="h-3.5 w-3.5" /> Op Notes
              </TabsTrigger>
              <TabsTrigger value="maintenance" className="rounded-none data-[state=active]:bg-background border-r last:border-r-0 font-mono text-xs px-6 h-full">
                Maintenance
              </TabsTrigger>
              <TabsTrigger value="priorities" className="rounded-none data-[state=active]:bg-background border-r last:border-r-0 font-mono text-xs px-6 h-full">
                Priorities
              </TabsTrigger>
              <TabsTrigger value="zones" className="rounded-none data-[state=active]:bg-background border-r last:border-r-0 font-mono text-xs px-6 h-full">
                Zones
              </TabsTrigger>
              <TabsTrigger value="telemetry" className="rounded-none data-[state=active]:bg-background border-r last:border-r-0 font-mono text-xs px-6 h-full">
                Telemetry
              </TabsTrigger>
            </TabsList>
          </div>

          <TabsContent value="notes" className="flex-1 p-6 m-0 overflow-auto bg-muted/10">
            <div className="max-w-4xl mx-auto space-y-6">
              <div className="bg-card border rounded-sm p-6 shadow-sm">
                <div className="flex items-center gap-3 mb-6 pb-4 border-b">
                  <div className="h-10 w-10 bg-muted rounded-full flex items-center justify-center text-muted-foreground">
                    <ShieldAlert className="h-5 w-5" />
                  </div>
                  <div>
                    <h2 className="font-bold text-lg">System Audit Notes</h2>
                    <p className="text-sm font-mono text-muted-foreground">Attached to review dataset</p>
                  </div>
                </div>
                <div className="font-mono text-sm leading-relaxed whitespace-pre-wrap">
                  {overview?.notes || "No notes available in this overview."}
                </div>
              </div>
            </div>
          </TabsContent>
          
          <TabsContent value="maintenance" className="flex-1 m-0 h-full">
            <RecordBrowser dataset="maintenance" title="Maintenance Log" description="Equipment and infrastructure maintenance schedules." />
          </TabsContent>

          <TabsContent value="priorities" className="flex-1 m-0 h-full">
            <RecordBrowser dataset="priorities" title="Task Priorities" description="Legacy priority weighting matrices." />
          </TabsContent>

          <TabsContent value="zones" className="flex-1 m-0 h-full">
            <RecordBrowser dataset="zones" title="Zone Configurations" description="Physical warehouse zone delineations." />
          </TabsContent>

          <TabsContent value="telemetry" className="flex-1 m-0 h-full">
            <RecordBrowser dataset="telemetry" title="Raw Telemetry" description="Unprocessed stream records from sensor network." />
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}
