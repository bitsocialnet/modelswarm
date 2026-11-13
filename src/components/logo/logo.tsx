import { useId } from 'react';
import { GAP_STROKE, PIECES, TRANSFORM } from './pieces';

type LogoProps = {
  size?: number;
  className?: string;
};

export function Logo({ size = 24, className }: LogoProps) {
  // Each Logo on the page needs its own mask id; useId's punctuation is not safe inside url(#...).
  const maskId = `logo-gap-${useId().replace(/[^a-zA-Z0-9_-]/g, '')}`;
  return (
    <svg className={className} width={size} height={size} viewBox='-20 0 430 430' aria-hidden='true' focusable='false'>
      <defs>
        <mask id={maskId} maskUnits='userSpaceOnUse' x={-20} y={0} width={430} height={430}>
          <rect x={-20} width={430} height={430} fill='white' />
          <path d={PIECES} transform={TRANSFORM} fill='none' stroke='black' strokeWidth={GAP_STROKE} strokeLinejoin='round' />
        </mask>
      </defs>
      <g mask={`url(#${maskId})`}>
        <path d={PIECES} transform={TRANSFORM} fill='var(--accent)' />
      </g>
    </svg>
  );
}
