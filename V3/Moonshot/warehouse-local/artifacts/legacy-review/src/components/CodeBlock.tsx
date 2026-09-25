import React, { useState } from 'react';
import { Check, Copy } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';

interface CodeBlockProps {
  code: string;
  language?: string;
  className?: string;
}

export function CodeBlock({ code, language = 'python', className }: CodeBlockProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className={cn("relative rounded-sm overflow-hidden border bg-[#1E1E1E]", className)}>
      <div className="flex items-center justify-between px-4 py-2 bg-[#2D2D2D] border-b border-[#404040]">
        <span className="text-xs font-mono text-gray-400">{language}</span>
        <Button 
          variant="ghost" 
          size="icon" 
          className="h-6 w-6 text-gray-400 hover:text-white hover:bg-[#404040]"
          onClick={handleCopy}
        >
          {copied ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
        </Button>
      </div>
      <div className="p-4 overflow-auto max-h-[500px]">
        <pre className="text-xs font-mono text-gray-300">
          <code>{code}</code>
        </pre>
      </div>
    </div>
  );
}
