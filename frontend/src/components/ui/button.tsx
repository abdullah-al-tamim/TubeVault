import * as React from 'react';
import {Slot} from '@radix-ui/react-slot';
import {cva, type VariantProps} from 'class-variance-authority';
import {cn} from '../../lib/utils';
const variants=cva('button',{variants:{variant:{default:'primary',outline:'outline',ghost:'ghost'}},defaultVariants:{variant:'default'}});
interface Props extends React.ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof variants>{asChild?:boolean}
export const Button=React.forwardRef<HTMLButtonElement,Props>(({className,variant,asChild=false,...props},ref)=>{const Comp=asChild?Slot:'button';return <Comp className={cn(variants({variant}),className)} ref={ref} {...props}/>});
Button.displayName='Button';
