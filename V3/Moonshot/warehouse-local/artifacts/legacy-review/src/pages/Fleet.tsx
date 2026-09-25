import React from 'react';
import { RecordBrowser } from '@/components/RecordBrowser';

export function Fleet() {
  return (
    <RecordBrowser 
      dataset="robots" 
      title="Fleet Records" 
      description="Inspect robot registry fields and review flags from the synthetic snapshot. Telemetry records are available under Evidence." 
    />
  );
}
