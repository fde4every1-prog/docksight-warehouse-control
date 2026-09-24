import * as React from "react"
import { cn } from "@/lib/utils"

const badgeVariants = (variant: string = "default") => {
  const base = "inline-flex items-center rounded-sm border px-2.5 py-0.5 text-xs font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2"
  
  const variants: Record<string, string> = {
    default: "border-transparent bg-primary text-primary-foreground hover:bg-primary/80",
    secondary: "border-transparent bg-secondary text-secondary-foreground hover:bg-secondary/80",
    destructive: "border-transparent bg-destructive text-destructive-foreground hover:bg-destructive/80",
    outline: "text-foreground font-mono font-normal",
    warning: "border-transparent bg-warning text-warning-foreground hover:bg-warning/80",
    success: "border-transparent bg-success text-success-foreground hover:bg-success/80",
  }

  return cn(base, variants[variant])
}

export interface BadgeProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: "default" | "secondary" | "destructive" | "outline" | "warning" | "success"
}

function Badge({ className, variant = "default", ...props }: BadgeProps) {
  return (
    <div className={cn(badgeVariants(variant), className)} {...props} />
  )
}

export { Badge, badgeVariants }
