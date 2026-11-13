import { Fragment } from 'react';

// Renders `backtick` spans in short copy strings as <code>.
export function inlineCode(text: string) {
  return text.split('`').map((part, i) => (i % 2 === 1 ? <code key={i}>{part}</code> : <Fragment key={i}>{part}</Fragment>));
}
