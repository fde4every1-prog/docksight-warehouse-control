import React from 'react';
import { RecordBrowser } from '@/components/RecordBrowser';

export function Tasks() {
  return (
    <RecordBrowser 
      dataset="tasks" 
      title="Task Confict Analyzer" 
      description="View task states, site annotations, and legacy dispatch rules that led to synthetic conflict flags." 
    />
  );
}
