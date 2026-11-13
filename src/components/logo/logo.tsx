// The mark is a 5x5 piece map. Lit pieces spell M; the centre one is still arriving.
const PATTERN = ['10001', '11011', '10201', '10001', '10001'];
const CELL = 8;
const STEP = 10;

type LogoProps = {
  size?: number;
  className?: string;
};

export function Logo({ size = 24, className }: LogoProps) {
  return (
    <svg className={className} width={size} height={size} viewBox='-1 -1 50 50' aria-hidden='true' focusable='false'>
      {PATTERN.flatMap((row, y) =>
        [...row].map((cell, x) => (
          <rect
            key={`${x}-${y}`}
            x={x * STEP}
            y={y * STEP}
            width={CELL}
            height={CELL}
            rx={0.6}
            fill={cell === '2' ? 'var(--accent-hot)' : 'var(--accent)'}
            fillOpacity={cell === '0' ? 0.16 : 1}
          />
        )),
      )}
    </svg>
  );
}
