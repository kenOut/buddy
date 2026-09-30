"use client";

import { motion } from "motion/react";
import type { ComponentProps } from "react";
import clsx from "clsx";

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "md" | "sm";

interface ButtonProps extends ComponentProps<typeof motion.button> {
  variant?: Variant;
  size?: Size;
}

const variantClasses: Record<Variant, string> = {
  primary:
    "bg-buddy-primary text-white shadow-lg shadow-buddy-primary/25 hover:bg-buddy-primary-dark",
  secondary:
    "bg-buddy-surface text-foreground border border-buddy-border hover:border-buddy-primary/50",
  ghost: "bg-transparent text-buddy-muted hover:text-foreground",
  danger:
    "bg-buddy-surface text-buddy-coral border border-buddy-border hover:border-buddy-coral hover:bg-buddy-coral/10",
};

const sizeClasses: Record<Size, string> = {
  md: "px-6 py-3 text-sm",
  sm: "px-4 py-1.5 text-xs",
};

export function Button({ variant = "primary", size = "md", className, children, ...props }: ButtonProps) {
  return (
    <motion.button
      whileHover={{ scale: props.disabled ? 1 : 1.03 }}
      whileTap={{ scale: props.disabled ? 1 : 0.97 }}
      className={clsx(
        "inline-flex items-center justify-center gap-2 rounded-full font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50",
        sizeClasses[size],
        variantClasses[variant],
        className
      )}
      {...props}
    >
      {children}
    </motion.button>
  );
}
