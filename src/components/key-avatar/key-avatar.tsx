import styles from './key-avatar.module.css';

const SIZE = 5;

// 32-bit FNV-1a, enough to spread a key or a name over a few dozen cells.
function hash(value: string, seed: number) {
  let h = 0x811c9dc5 ^ seed;
  for (let i = 0; i < value.length; i += 1) {
    h ^= value.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  return h >>> 0;
}

// A piece map drawn from a key or a name: a mirrored 5x5 grid of verified and pending pieces, so the
// same identity always gets the same mark. It is decoration, not a fingerprint to compare by eye.
export function KeyAvatar({ value, size = 48, className }: { value: string; size?: number; className?: string }) {
  const bits = hash(value, 0) ^ (hash(value, 7) << 7);
  const cells: boolean[] = [];
  for (let row = 0; row < SIZE; row += 1) {
    for (let col = 0; col < 3; col += 1) cells.push(Boolean((bits >>> (row * 3 + col)) & 1));
  }
  const lit = (row: number, col: number) => cells[row * 3 + (col < 3 ? col : SIZE - 1 - col)];
  return (
    <svg className={`${styles.avatar} ${className ?? ''}`} width={size} height={size} viewBox='0 0 60 60' aria-hidden='true' focusable='false'>
      <rect width='60' height='60' rx='10' className={styles.ground} />
      {Array.from({ length: SIZE * SIZE }, (_, i) => {
        const row = Math.floor(i / SIZE);
        const col = i % SIZE;
        return <rect key={i} x={7 + col * 9.6} y={7 + row * 9.6} width='8' height='8' rx='1.2' className={lit(row, col) ? styles.on : styles.off} />;
      })}
    </svg>
  );
}
