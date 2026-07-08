import React from 'react';
import { cn } from '../../utils/cn';
import { Loader2 } from 'lucide-react';

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'outline' | 'ghost' | 'danger';
  size?: 'sm' | 'md' | 'lg' | 'icon';
  isLoading?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = 'primary', size = 'md', isLoading, children, disabled, ...props }, ref) => {
    const variants = {
      primary:
        'bg-primary text-primary-foreground hover:bg-primary-hover disabled:bg-border disabled:text-primary-foreground',
      secondary: 'bg-secondary text-primary hover:bg-accent disabled:opacity-50',
      outline: 'border border-secondary bg-card text-primary hover:border-border disabled:opacity-50',
      ghost: 'bg-transparent text-primary hover:bg-accent disabled:opacity-50',
      danger: 'bg-destructive text-destructive-foreground hover:bg-destructive/90 disabled:opacity-50',
    };

    const sizes = {
      // button small: padding 6px 12px, текст 14px/20px
      sm: 'px-3 py-1.5 text-sm leading-5',
      md: 'px-3 py-1.5 text-sm leading-5',
      // button big: padding 11px 16px, текст 16px
      lg: 'px-4 py-[11px] text-base leading-none',
      icon: 'h-10 w-10 flex items-center justify-center p-0',
    };

    return (
      <button
        ref={ref}
        className={cn(
          'inline-flex items-center justify-center gap-2 rounded-lg font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none',
          variants[variant],
          sizes[size],
          className
        )}
        disabled={disabled || isLoading}
        {...props}
      >
        {isLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
        {children}
      </button>
    );
  }
);
Button.displayName = 'Button';
