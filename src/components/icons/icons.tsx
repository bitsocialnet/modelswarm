import type { ReactNode } from 'react';

// One stroke icon set for the site: 16-unit grid, 1.5 stroke, round joins. Decorative unless labelled by the caller.
type IconProps = { size?: number; className?: string };

function Icon({ size = 16, className, children }: IconProps & { children: ReactNode }) {
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox='0 0 16 16'
      fill='none'
      stroke='currentColor'
      strokeWidth='1.5'
      strokeLinecap='round'
      strokeLinejoin='round'
      aria-hidden='true'
      focusable='false'
    >
      {children}
    </svg>
  );
}

export const DownloadIcon = (props: IconProps) => (
  <Icon {...props}>
    <path d='M8 2v8.5M4.5 7 8 10.5 11.5 7M2.5 13.5h11' />
  </Icon>
);

export const ChevronDownIcon = (props: IconProps) => (
  <Icon {...props}>
    <path d='m4 6 4 4 4-4' />
  </Icon>
);

export const ArrowRightIcon = (props: IconProps) => (
  <Icon {...props}>
    <path d='M2.5 8h11M9.5 4l4 4-4 4' />
  </Icon>
);

export const SearchIcon = (props: IconProps) => (
  <Icon {...props}>
    <circle cx='7' cy='7' r='4.5' />
    <path d='m10.5 10.5 3 3' />
  </Icon>
);

export const CheckIcon = (props: IconProps) => (
  <Icon {...props}>
    <path d='m3 8.5 3.2 3L13 4.5' />
  </Icon>
);

export const CrossIcon = (props: IconProps) => (
  <Icon {...props}>
    <path d='m4 4 8 8M12 4l-8 8' />
  </Icon>
);

export const PlusIcon = (props: IconProps) => (
  <Icon {...props}>
    <path d='M8 3v10M3 8h10' />
  </Icon>
);

// Two peers exchanging pieces: the seeder count glyph.
export const SeedIcon = (props: IconProps) => (
  <Icon {...props}>
    <path d='M8 14V8M8 8C8 5 6 3.5 3 3.5 3 6.5 5 8 8 8ZM8 9.5c0-2.6 1.8-4 4.8-4-.1 2.8-1.9 4-4.8 4Z' />
  </Icon>
);

export const KeyIcon = (props: IconProps) => (
  <Icon {...props}>
    <circle cx='5' cy='11' r='2.75' />
    <path d='M7 9 13.5 2.5M11 5l2 2M9.5 6.5l1.5 1.5' />
  </Icon>
);

export const FileIcon = (props: IconProps) => (
  <Icon {...props}>
    <path d='M3.5 1.5h6l3 3v10h-9z' />
    <path d='M9.5 1.5v3h3' />
  </Icon>
);

export const GitHubMark = ({ size = 15 }: { size?: number }) => (
  <svg width={size} height={size} viewBox='0 0 16 16' aria-hidden='true' focusable='false'>
    <path
      fill='currentColor'
      d='M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8Z'
    />
  </svg>
);
