import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const badgeVariants = cva("badge", {
  variants: {
    variant: {
      default: "",
      green: "badge-green",
      blue: "badge-blue"
    },
    dot: {
      true: "badge-dot",
      false: ""
    }
  },
  defaultVariants: {
    variant: "default",
    dot: false
  }
});

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, dot, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant, dot, className }))} {...props} />;
}

export { Badge, badgeVariants };
